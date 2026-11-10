"""Como o texto fixo se refere ao analista: pelo nome de exibição da configuração, ou de forma genérica.

Devolve texto cru. O nome vem de configuração e é texto de terceiros: quem o põe em HTML ou em prompt
escapa uma vez só, no ponto de saída (o bot já escapa o que recebe, os prompts usam html.escape)."""
from quilate.config import Settings


def subject(settings: Settings) -> str:
    """Sujeito da frase: "Ana falou de BTC." ou "O analista falou de BTC."."""
    return settings.analyst_name.strip() or "O analista"


def of(settings: Settings) -> str:
    """Complemento com "de": "manual das estratégias de Ana" ou "do analista"."""
    name = settings.analyst_name.strip()
    return f"de {name}" if name else "do analista"
