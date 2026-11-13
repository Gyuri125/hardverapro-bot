"""Adatmodellek."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Specs:
    """A hirdetés szövegéből kinyert hardver-információk.

    Minden mező lehet None / üres, ha nem sikerült felismerni.
    """

    gpus: list[str] = field(default_factory=list)
    cpu: str | None = None
    ram_gb: int | None = None
    storage_gb: int | None = None
    refresh_hz: int | None = None
    screen_inch: float | None = None
    is_new: bool = False
    warranty: bool = False

    def summary(self) -> str:
        """Rövid, emberi összefoglaló a Discord üzenethez."""
        parts: list[str] = []
        if self.cpu:
            parts.append(self.cpu)
        if self.gpus:
            parts.append(self.gpus[0].upper().replace("RTX", "RTX").replace("GTX", "GTX"))
        if self.ram_gb:
            parts.append(f"{self.ram_gb} GB RAM")
        if self.storage_gb:
            parts.append(f"{self.storage_gb} GB SSD" if self.storage_gb < 1024 else f"{self.storage_gb // 1024} TB SSD")
        if self.screen_inch:
            parts.append(f"{self.screen_inch:g}\"")
        if self.refresh_hz:
            parts.append(f"{self.refresh_hz} Hz")
        if self.is_new:
            parts.append("ÚJ")
        if self.warranty:
            parts.append("garanciás")
        return " · ".join(parts)

    @property
    def gpu_tier(self) -> int:
        """0-5 közötti kategória a GPU modellszámából (durva közelítés)."""
        return max((_gpu_tier(gpu) for gpu in self.gpus), default=0)


_GENERATION_TABLE: dict[int, dict[int, int]] = {
    50: {90: 5, 80: 5, 70: 4, 60: 3, 50: 3},
    40: {90: 5, 80: 5, 70: 4, 60: 3, 50: 2},
    30: {90: 4, 80: 4, 70: 3, 60: 2, 50: 1},
    20: {90: 3, 80: 3, 70: 2, 60: 1, 50: 1},
    16: {60: 1, 50: 1},
    10: {80: 1, 70: 1},
}


def _gpu_tier(gpu: str) -> int:
    """'rtx 4060' -> 3, 'rtx 5090' -> 5, 'rx 7800' -> 4, ismeretlen -> 0."""
    model = gpu.split()[-1]
    digits = "".join(ch for ch in model if ch.isdigit())
    if not digits:
        return 0
    number = int(digits)

    if gpu.startswith("rx"):
        if number >= 7900:
            return 5
        if number >= 7800:
            return 4
        if number >= 7600:
            return 3
        if number >= 6600:
            return 2
        return 1
    if gpu.startswith("arc"):
        return 2

    generation, klass = divmod(number, 100)
    tier = _GENERATION_TABLE.get(generation, {}).get(klass)
    if tier is not None:
        return tier
    # ismeretlen modellszám: generáció alapján óvatos becslés
    if 40 <= generation <= 59:
        return 2
    if 30 <= generation < 40:
        return 1
    return 0


@dataclass
class Listing:
    """Egy hirdetés (listaoldalról, opcionálisan részoldallal kiegészítve)."""

    uadid: str
    title: str
    url: str
    price: int | None = None
    seller: str = ""
    seller_rating: int = 0
    is_business: bool = False
    location: str = ""
    posted: str = ""
    ribbons: list[str] = field(default_factory=list)
    promoted: bool = False
    condition: str = ""
    intent: str = ""
    description: str = ""
    shipping: bool = False

    specs: Specs = field(default_factory=Specs)

    @property
    def text(self) -> str:
        return f"{self.title} {self.description}".strip()

    @property
    def url_abs(self) -> str:
        if self.url.startswith("http"):
            return self.url
        return "https://hardverapro.hu" + self.url


@dataclass
class Hit:
    """Egy értesítésre érdemes találat."""

    listing: Listing
    profile: str
    score: int
    reasons: list[str] = field(default_factory=list)
    target_price: int | None = None
    market_median: int | None = None
