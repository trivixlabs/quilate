def normalize_asset(raw: str, known: set[str], aliases: dict[str, str]) -> str:
    """Nome canônico do ativo: apelido, depois prefixo LD (Binance Earn) só se o resto é conhecido."""
    s = raw.upper()
    s = aliases.get(s, s)
    if s.startswith("LD") and s not in known and s[2:] in known:
        return s[2:]
    return s
