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
        for gpu in self.gpus:
            digits = "".join(ch for ch in gpu if ch.isdigit())
            if not digits:
                continue
            num = int(digits[:4])
            if num >= 5080:
                return 5
            if num >= 5070:
                return 4
            if num >= 4070:
                return 4
            if num >= 4060:
                return 3
            if num >= 3070:
                return 3
            if num >= 3060:
                return 2
            if num >= 2000:
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
