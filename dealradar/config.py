"""A config.yaml betöltése és validálása."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class ConfigError(Exception):
    """Hibás konfiguráció."""


def load_dotenv(path: str | Path | None = None) -> bool:
    """Egyszerű `.env` beolvasó, külső csomag nélkül.

    - csak akkor állít be egy változót, ha az még nincs a környezetben
      (tehát a GitHub Secret / exportált változó mindig erősebb),
    - támogatja a `#` kommenteket, az üres sorokat és az idézőjeleket,
    - ha nincs fájl, csendben nem csinál semmit.

    Visszaadja, hogy talált-e és beolvasott-e fájlt.
    """
    file = Path(path) if path else Path(".env")
    if not file.is_file():
        return False

    try:
        content = file.read_text(encoding="utf-8-sig")
    except OSError:
        return False

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export ") :].strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value
    return True


# --------------------------------------------------------------------------
#  settings
# --------------------------------------------------------------------------


@dataclass
class Settings:
    request_delay: float = 1.5
    timeout: int = 20
    retries: int = 3
    webhook_env: str = "DISCORD_WEBHOOK_URL"
    min_score: int = 50
    max_notifications: int = 20
    state_file: str = "state/seen.json"
    state_retention_days: int = 60
    renotify_price_drop_percent: int = 10
    deep_scan: bool = True
    deep_scan_limit: int = 40

    @property
    def webhook_url(self) -> str | None:
        return os.environ.get(self.webhook_env) or None


# --------------------------------------------------------------------------
#  watch + filters
# --------------------------------------------------------------------------


@dataclass
class WatchedFilters:
    min_price: int = 0
    max_price: int = 10**9
    exclude_keywords: list[str] = field(default_factory=list)
    include_keywords: list[str] = field(default_factory=list)
    exclude_promoted: bool = True
    allow_business: bool = True
    min_seller_rating: int | None = None
    locations: list[str] = field(default_factory=list)
    # "any" = mindegy; "hu" = a kifejezetten külföldi billentyűzetű gépeket kiszűri
    keyboard: str = "any"


@dataclass
class Watch:
    name: str
    url: str
    max_pages: int = 2
    filters: WatchedFilters = field(default_factory=WatchedFilters)


# --------------------------------------------------------------------------
#  profile
# --------------------------------------------------------------------------


@dataclass
class ProfileSpecs:
    gpu_any: list[str] = field(default_factory=list)
    cpu_any: list[str] = field(default_factory=list)
    min_ram_gb: int = 0
    min_storage_gb: int = 0
    min_refresh_hz: int = 0
    # Ha true: amit nem ismerünk fel, az nem illeszkedik (szigorú).
    # Ha false: az ismeretlen érték nem utasítja el a hirdetést.
    strict: bool = False


@dataclass
class Profile:
    name: str
    any_keywords: list[str] = field(default_factory=list)
    all_keywords: list[str] = field(default_factory=list)
    none_keywords: list[str] = field(default_factory=list)
    min_price: int = 0
    max_price: int = 10**9
    deal_price: int | None = None
    specs: ProfileSpecs = field(default_factory=ProfileSpecs)


# --------------------------------------------------------------------------
#  market compare
# --------------------------------------------------------------------------


@dataclass
class MarketCompare:
    enabled: bool = True
    group_by: str = "gpu"
    min_samples: int = 10
    good_deal_discount: float = 0.20


@dataclass
class Config:
    settings: Settings = field(default_factory=Settings)
    watches: list[Watch] = field(default_factory=list)
    profiles: list[Profile] = field(default_factory=list)
    market: MarketCompare = field(default_factory=MarketCompare)

    def profile_names(self) -> list[str]:
        return [p.name for p in self.profiles]


# --------------------------------------------------------------------------
#  betöltés
# --------------------------------------------------------------------------


def _require_mapping(value: Any, where: str) -> dict:
    if not isinstance(value, dict):
        raise ConfigError(f"{where}: szótár (kulcs: érték) kell, nem {type(value).__name__}")
    return value


def _as_int(value: Any, where: str, default: int | None = None) -> int:
    if value is None:
        if default is None:
            raise ConfigError(f"{where}: hiányzó számérték")
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{where}: egész szám kell, ez nem az: {value!r}") from exc


def _as_float(value: Any, where: str, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{where}: szám kell, ez nem az: {value!r}") from exc


def _as_bool(value: Any, where: str, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raise ConfigError(f"{where}: true/false kell, ez nem az: {value!r}")


def _as_str_list(value: Any, where: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        raise ConfigError(f"{where}: lista kell (pl. [alma, körte])")
    out: list[str] = []
    for item in value:
        if not isinstance(item, (str, int, float)):
            raise ConfigError(f"{where}: csak szöveg/szám lehet a listában: {item!r}")
        text = str(item).strip()
        if text:
            out.append(text)
    return out


def _as_keyboard(value: Any, where: str) -> str:
    if value is None:
        return "any"
    text = str(value).strip().lower()
    if text in {"any", "mindegy", "mind"}:
        return "any"
    if text in {"hu", "hun", "magyar"}:
        return "hu"
    raise ConfigError(f"{where}: 'any' vagy 'hu' lehet, ez nem az: {value!r}")


def _load_filters(raw: Any, where: str) -> WatchedFilters:
    if raw is None:
        return WatchedFilters()
    data = _require_mapping(raw, where)
    return WatchedFilters(
        min_price=_as_int(data.get("min_price"), f"{where}.min_price", 0),
        max_price=_as_int(data.get("max_price"), f"{where}.max_price", 10**9),
        exclude_keywords=_as_str_list(data.get("exclude_keywords"), f"{where}.exclude_keywords"),
        include_keywords=_as_str_list(data.get("include_keywords"), f"{where}.include_keywords"),
        exclude_promoted=_as_bool(data.get("exclude_promoted"), f"{where}.exclude_promoted", True),
        allow_business=_as_bool(data.get("allow_business"), f"{where}.allow_business", True),
        min_seller_rating=(
            None
            if data.get("min_seller_rating") is None
            else _as_int(data.get("min_seller_rating"), f"{where}.min_seller_rating")
        ),
        locations=_as_str_list(data.get("locations"), f"{where}.locations"),
        keyboard=_as_keyboard(data.get("keyboard"), f"{where}.keyboard"),
    )


def _load_watch(raw: Any, index: int, defaults: WatchedFilters) -> Watch:
    where = f"watches[{index}]"
    data = _require_mapping(raw, where)
    name = str(data.get("name") or f"watch-{index + 1}").strip()
    url = str(data.get("url") or "").strip()
    if not url.startswith("http"):
        raise ConfigError(f"{where}.url: teljes http(s) URL kell")
    max_pages = _as_int(data.get("max_pages"), f"{where}.max_pages", 2)
    if max_pages < 1:
        raise ConfigError(f"{where}.max_pages: legalább 1 kell")
    filters = _load_filters(data.get("filters"), f"{where}.filters") if data.get("filters") else defaults
    return Watch(name=name, url=url, max_pages=max_pages, filters=filters)


def _load_specs(raw: Any, where: str) -> ProfileSpecs:
    if raw is None:
        return ProfileSpecs()
    data = _require_mapping(raw, where)
    return ProfileSpecs(
        gpu_any=_as_str_list(data.get("gpu_any"), f"{where}.gpu_any"),
        cpu_any=_as_str_list(data.get("cpu_any"), f"{where}.cpu_any"),
        min_ram_gb=_as_int(data.get("min_ram_gb"), f"{where}.min_ram_gb", 0),
        min_storage_gb=_as_int(data.get("min_storage_gb"), f"{where}.min_storage_gb", 0),
        min_refresh_hz=_as_int(data.get("min_refresh_hz"), f"{where}.min_refresh_hz", 0),
        strict=_as_bool(data.get("strict"), f"{where}.strict", False),
    )


def _load_profile(raw: Any, index: int) -> Profile:
    where = f"profiles[{index}]"
    data = _require_mapping(raw, where)
    name = str(data.get("name") or f"profile-{index + 1}").strip()
    profile = Profile(
        name=name,
        any_keywords=_as_str_list(data.get("any_keywords"), f"{where}.any_keywords"),
        all_keywords=_as_str_list(data.get("all_keywords"), f"{where}.all_keywords"),
        none_keywords=_as_str_list(data.get("none_keywords"), f"{where}.none_keywords"),
        min_price=_as_int(data.get("min_price"), f"{where}.min_price", 0),
        max_price=_as_int(data.get("max_price"), f"{where}.max_price", 10**9),
        deal_price=(
            None
            if data.get("deal_price") is None
            else _as_int(data.get("deal_price"), f"{where}.deal_price")
        ),
        specs=_load_specs(data.get("specs"), f"{where}.specs"),
    )
    if not (
        profile.any_keywords
        or profile.all_keywords
        or profile.specs.gpu_any
        or profile.specs.cpu_any
        or profile.specs.min_ram_gb
        or profile.specs.min_storage_gb
    ):
        raise ConfigError(
            f"{where}: a profil semmire nem illeszkedne – kell legalább egy "
            f"any_keywords / all_keywords / specs megkötés"
        )
    if profile.min_price > profile.max_price:
        raise ConfigError(f"{where}: min_price nagyobb, mint max_price")
    return profile


def load_config(path: str | Path) -> Config:
    """Beolvassa és validálja a YAML konfigurációt."""
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"Nincs ilyen konfigurációs fájl: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"Hibás YAML a {path} fájlban: {exc}") from exc

    data = _require_mapping(raw, str(path))

    s = _require_mapping(data.get("settings") or {}, "settings")
    settings = Settings(
        request_delay=max(0.0, _as_float(s.get("request_delay"), "settings.request_delay", 1.5)),
        timeout=_as_int(s.get("timeout"), "settings.timeout", 20),
        retries=_as_int(s.get("retries"), "settings.retries", 3),
        webhook_env=str(s.get("webhook_env") or "DISCORD_WEBHOOK_URL"),
        min_score=_as_int(s.get("min_score"), "settings.min_score", 50),
        max_notifications=_as_int(s.get("max_notifications"), "settings.max_notifications", 20),
        state_file=str(s.get("state_file") or "state/seen.json"),
        state_retention_days=_as_int(s.get("state_retention_days"), "settings.state_retention_days", 60),
        renotify_price_drop_percent=_as_int(
            s.get("renotify_price_drop_percent"), "settings.renotify_price_drop_percent", 10
        ),
        deep_scan=_as_bool(s.get("deep_scan"), "settings.deep_scan", True),
        deep_scan_limit=_as_int(s.get("deep_scan_limit"), "settings.deep_scan_limit", 40),
    )

    global_filters = _load_filters(data.get("filters"), "filters") if data.get("filters") else WatchedFilters()

    watches_raw = data.get("watches") or []
    if not isinstance(watches_raw, list) or not watches_raw:
        raise ConfigError("watches: legalább egy figyelt kategória/URL kell")
    watches = [_load_watch(w, i, global_filters) for i, w in enumerate(watches_raw)]

    profiles_raw = data.get("profiles") or []
    if not isinstance(profiles_raw, list) or not profiles_raw:
        raise ConfigError("profiles: legalább egy profil kell (mi számít jó dealnek)")
    profiles = [_load_profile(p, i) for i, p in enumerate(profiles_raw)]

    m = _require_mapping(data.get("market_compare") or {}, "market_compare")
    market = MarketCompare(
        enabled=_as_bool(m.get("enabled"), "market_compare.enabled", True),
        group_by=str(m.get("group_by") or "gpu"),
        min_samples=_as_int(m.get("min_samples"), "market_compare.min_samples", 10),
        good_deal_discount=_as_float(m.get("good_deal_discount"), "market_compare.good_deal_discount", 0.20),
    )
    if market.group_by not in {"gpu", "cpu", "brand"}:
        raise ConfigError("market_compare.group_by: gpu / cpu / brand lehet")

    return Config(settings=settings, watches=watches, profiles=profiles, market=market)
