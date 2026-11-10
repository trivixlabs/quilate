"""Texto de página linkada pelo analista. Só host público, resolvido antes de baixar, sem seguir redirecionamento às cegas."""
import ipaddress
import logging
import socket
from urllib.parse import urljoin, urlsplit

import httpx

log = logging.getLogger(__name__)
MAX_HOPS = 5
TIMEOUT = 20.0
MAX_BYTES = 5 * 1024 * 1024


def _public(url: str) -> bool:
    """Só http(s) para host público. Recusa loopback, rede local e link-local (o próprio servir, o roteador).
    Nome de host é resolvido: todos os IPs precisam ser públicos."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or not host or host == "localhost" or host.endswith(".localhost"):
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    # ponytail: resolve aqui e o httpx resolve de novo; um DNS que troca a resposta entre as duas passa
    return bool(infos) and all(ipaddress.ip_address(i[4][0]).is_global for i in infos)


def fetch_text(url: str) -> str | None:
    """Texto principal da página, ou None. Cada salto de redirecionamento passa pela mesma checagem de host."""
    import trafilatura

    with httpx.Client(follow_redirects=False, timeout=TIMEOUT, headers={"User-Agent": "Mozilla/5.0"}) as http:
        for _ in range(MAX_HOPS):
            if not _public(url):
                return None
            r = http.get(url)
            if r.is_redirect and "location" in r.headers:
                url = urljoin(url, r.headers["location"])
                continue
            if r.status_code != 200 or len(r.content) > MAX_BYTES:
                return None
            return trafilatura.extract(r.text, url=url)
    return None
