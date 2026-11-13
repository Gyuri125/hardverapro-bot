"""Kattintható linkek generálása az értesítésekhez."""

from __future__ import annotations

import re
from urllib.parse import quote_plus

from .specs import norm

# Szavak, amik csak zajt jelentenek egy modell-keresésben.
_NOISE = {
    "elado", "eladó", "uj", "új", "hasznalt", "használt", "gamer", "laptop",
    "notebook", "akar", "akár", "akcio", "akció", "garancia", "gari", "magyar",
    "billentyuzet", "billentyűzet", "db", "darab", "surgos", "sürgős", "jo", "jó",
    "allapot", "állapot", "tokeletes", "tökéletes", "szep", "szép", "afas", "áfás",
    "szamla", "számla", "ujszeru", "újszerű", "bontott", "bontatlan", "csere",
    "nem", "erdekel", "érdekel", "fizet", "keszpenz", "készpénz", "komplett",
    "doboza", "doboz", "tartozek", "tartozék", "ajandek", "ajándék",
}

_TOKEN_RE = re.compile(r"[^\s/|,()\[\]]+")


def cpu_manufacturer_url(cpu: str | None) -> str | None:
    """A CPU gyártójának (Intel / AMD) keresőoldala."""
    if not cpu:
        return None
    n = norm(cpu)
    query = quote_plus(cpu)
    if n.startswith(("ryzen", "athlon", "threadripper", "a-series")):
        return f"https://www.amd.com/en/search.html?q={query}"
    if n.startswith(("i3", "i5", "i7", "i9", "ultra", "pentium", "celeron", "xeon")):
        return f"https://www.intel.com/content/www/us/en/products/search.html?q={query}"
    return None


def specs_query(title: str, max_tokens: int = 7) -> str:
    """A hirdetés címéből egy tiszta modell-keresőszöveg."""
    tokens = _TOKEN_RE.findall(title)
    keep = [t for t in tokens if norm(t) not in _NOISE and (len(t) > 1 or t.isdigit())]
    return " ".join(keep[:max_tokens]).strip()


def specs_url(title: str) -> str:
    """Keresőlink a laptop specifikációjához."""
    query = specs_query(title)
    if not query:
        query = title.strip()[:60]
    return "https://www.google.com/search?q=" + quote_plus(query + " specs")
