"""Szűrés, profil-illesztés, piaci medián és pontozás."""

from __future__ import annotations

import statistics

from .config import MarketCompare, Profile, WatchedFilters
from .models import Hit, Listing
from .specs import brand as detect_brand
from .specs import norm


# --------------------------------------------------------------------------
#  watch szűrők
# --------------------------------------------------------------------------


def passes_filters(listing: Listing, filters: WatchedFilters, *, final: bool = False) -> bool:
    """Kemény szűrők: ár, tiltott szavak, eladó, hely, hirdetés típusa.

    `final=False`: a cím alapján döntünk, a leírás még nem ismert.
    `final=True`:  a részoldal már beolvasva, ilyenkor az ismeretlen
                   képernyőméret is kizárható.
    """
    if listing.price is None:
        return False
    if listing.price < filters.min_price or listing.price > filters.max_price:
        return False
    if filters.exclude_promoted and listing.promoted:
        return False
    if not filters.allow_business and listing.is_business:
        return False
    if filters.min_seller_rating is not None and listing.seller_rating < filters.min_seller_rating:
        return False
    if listing.intent and "keres" in norm(listing.intent):
        return False
    if filters.keyboard == "hu" and listing.specs.keyboard == "foreign":
        return False

    if filters.min_screen_inch:
        screen = listing.specs.screen_inch
        if screen is None:
            if final and filters.screen_unknown == "reject":
                return False
        elif screen < filters.min_screen_inch:
            return False

    if filters.min_cpu_year:
        year = listing.specs.cpu_year
        if year is None:
            if final and filters.cpu_year_unknown == "reject":
                return False
        elif year < filters.min_cpu_year:
            return False

    if filters.min_memory_gen and listing.specs.memory_gen is not None:
        if listing.specs.memory_gen < filters.min_memory_gen:
            return False

    text = norm(listing.text)
    if filters.include_keywords and not any(norm(k) in text for k in filters.include_keywords):
        return False
    if any(norm(k) in text for k in filters.exclude_keywords):
        return False

    if filters.locations:
        location = norm(listing.location)
        if not any(norm(loc) in location for loc in filters.locations):
            return False

    return True


# --------------------------------------------------------------------------
#  profil illesztés
# --------------------------------------------------------------------------


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(norm(keyword) in text for keyword in keywords)


def _gpu_matches(listing: Listing, wanted: list[str]) -> bool:
    if not wanted:
        return True
    if not listing.specs.gpus:
        return False
    # Csak az első (hirdetett) GPU számít: bolt-leírásokban több gép is szerepel.
    primary = norm(listing.specs.gpus[0])
    return any(norm(w) in primary for w in wanted)


def _cpu_matches(listing: Listing, wanted: list[str]) -> bool:
    if not wanted:
        return True
    cpu = norm(listing.specs.cpu or "")
    if not cpu:
        return False
    return any(norm(w) in cpu for w in wanted)


def _min_ok(actual: int | None, required: int, strict: bool) -> bool:
    """minimum-kritérium; ismeretlen érték strict módban elutasít."""
    if not required:
        return True
    if actual is None:
        return not strict
    return actual >= required


def match_profile(listing: Listing, profile: Profile) -> tuple[bool, list[str]]:
    """Illeszkedik-e a hirdetés a profilra? Visszaadja az okokat is."""
    if listing.price is None:
        return False, []
    upper = profile.max_price
    if profile.stretch_max_price is not None and profile.stretch_max_price > upper:
        upper = profile.stretch_max_price
    if not (profile.min_price <= listing.price <= upper):
        return False, []

    text = norm(listing.text)
    if profile.none_keywords and _contains_any(text, profile.none_keywords):
        return False, []
    if profile.all_keywords and not all(norm(k) in text for k in profile.all_keywords):
        return False, []
    if profile.any_keywords and not _contains_any(text, profile.any_keywords):
        return False, []

    specs = profile.specs
    if not _gpu_matches(listing, specs.gpu_any):
        return False, []
    if not _cpu_matches(listing, specs.cpu_any):
        return False, []

    if not _min_ok(listing.specs.ram_gb, specs.min_ram_gb, specs.strict):
        return False, []
    if not _min_ok(listing.specs.storage_gb, specs.min_storage_gb, specs.strict):
        return False, []
    if not _min_ok(listing.specs.refresh_hz, specs.min_refresh_hz, specs.strict):
        return False, []

    reasons: list[str] = []
    if profile.any_keywords:
        reasons.append("egyezik: " + ", ".join(profile.any_keywords[:3]))
    if specs.gpu_any:
        reasons.append("GPU: " + ", ".join(listing.specs.gpus[:2]).upper())
    return True, reasons


def matches_any_profile(listing: Listing, profiles: list[Profile]) -> bool:
    return any(match_profile(listing, p)[0] for p in profiles)


# --------------------------------------------------------------------------
#  piaci medián
# --------------------------------------------------------------------------


def market_key(listing: Listing, compare: MarketCompare) -> str | None:
    if compare.group_by == "gpu":
        return norm(listing.specs.gpus[0]) if listing.specs.gpus else None
    if compare.group_by == "cpu":
        return norm(listing.specs.cpu) if listing.specs.cpu else None
    return detect_brand(listing.title)


def compute_market_medians(listings: list[Listing], compare: MarketCompare) -> dict[str, int]:
    """Csoportonkénti medián ár a MOST látott hirdetésekből."""
    if not compare.enabled:
        return {}
    groups: dict[str, list[int]] = {}
    for listing in listings:
        if listing.price is None or listing.price <= 0:
            continue
        key = market_key(listing, compare)
        if not key:
            continue
        groups.setdefault(key, []).append(listing.price)

    medians: dict[str, int] = {}
    for key, prices in groups.items():
        if len(prices) >= compare.min_samples:
            medians[key] = int(statistics.median(prices))
    return medians


# --------------------------------------------------------------------------
#  pontozás
# --------------------------------------------------------------------------


def _spec_points(listing: Listing) -> tuple[int, list[str]]:
    specs = listing.specs
    points = 0
    reasons: list[str] = []

    if specs.ram_gb and specs.ram_gb >= 32:
        points += 6
        reasons.append(f"{specs.ram_gb} GB RAM")
    elif specs.ram_gb and specs.ram_gb >= 16:
        points += 3
        reasons.append(f"{specs.ram_gb} GB RAM")

    if specs.storage_gb and specs.storage_gb >= 1024:
        points += 5
        reasons.append(f"{specs.storage_gb // 1024} TB SSD")
    elif specs.storage_gb and specs.storage_gb >= 512:
        points += 3

    if specs.refresh_hz and specs.refresh_hz >= 165:
        points += 4
        reasons.append(f"{specs.refresh_hz} Hz")
    elif specs.refresh_hz and specs.refresh_hz >= 120:
        points += 2

    tier = specs.gpu_tier
    if tier >= 4:
        points += 5
    elif tier == 3:
        points += 3
    elif tier == 2:
        points += 1

    if specs.is_new:
        points += 4
        reasons.append("új / bontatlan")
    if specs.warranty:
        points += 4
        reasons.append("garanciás")
    if specs.oled:
        points += 3
        reasons.append("OLED")
    if specs.keyboard == "hu":
        points += 3
        reasons.append("magyar billentyűzet")

    return min(points, 20), reasons


def _price_points(price: int, target: int) -> tuple[int, float]:
    """0..45 pont. A célár körül is ad pontot, hogy ne legyen szakadék."""
    if target <= 0:
        return 0, 0.0
    ratio = (target - price) / target
    scaled = (ratio + 0.10) / 0.30
    return int(min(max(scaled, 0.0), 1.0) * 45), ratio


def score(
    listing: Listing,
    profile: Profile,
    compare: MarketCompare,
    median: int | None,
) -> Hit | None:
    matched, reasons = match_profile(listing, profile)
    if not matched or listing.price is None:
        return None

    points = 40
    spec_points, spec_reasons = _spec_points(listing)
    points += spec_points
    reasons.extend(spec_reasons)

    over_budget = bool(
        profile.stretch_max_price
        and listing.price is not None
        and listing.price > profile.max_price
    )
    if over_budget:
        points -= 5
        reasons.insert(
            0,
            f"keret felett: {listing.price:,} Ft (keret {profile.max_price:,} Ft)".replace(",", " "),
        )

    targets: list[int] = []
    if profile.deal_price:
        targets.append(profile.deal_price)
    if compare.enabled and median:
        market_target = int(median * (1 - compare.good_deal_discount))
        targets.append(market_target)
    target = max(targets) if targets else None

    if target:
        price_points, ratio = _price_points(listing.price, target)
        points += price_points
        if ratio > 0:
            reasons.insert(
                0,
                f"ár {ratio * 100:.0f}%-kal a célár alatt "
                f"({listing.price:,} Ft / {target:,} Ft)".replace(",", " "),
            )
        elif ratio > -0.10:
            reasons.insert(
                0,
                f"ár a célár körül ({listing.price:,} Ft / {target:,} Ft)".replace(",", " "),
            )

    if median and listing.price <= median * (1 - compare.good_deal_discount):
        reasons.append(f"piaci medián {median:,} Ft".replace(",", " "))

    suspicious = bool(
        compare.enabled
        and median
        and listing.price is not None
        and listing.price <= median * compare.cheap_threshold
    )
    if suspicious:
        reasons.append("gyanúsan olcsó a piaci mediánhoz képest")

    points = max(0, min(100, points))
    return Hit(
        listing=listing,
        profile=profile.name,
        score=points,
        reasons=reasons,
        target_price=target,
        market_median=median,
        over_budget=over_budget,
        budget=profile.max_price,
        suspiciously_cheap=suspicious,
    )


def best_hit(
    listing: Listing,
    profiles: list[Profile],
    compare: MarketCompare,
    medians: dict[str, int],
) -> Hit | None:
    """A legjobb pontszámú profil-találat egy hirdetésre."""
    key = market_key(listing, compare)
    median = medians.get(key) if key else None
    hits = [h for p in profiles if (h := score(listing, p, compare, median)) is not None]
    if not hits:
        return None
    return max(hits, key=lambda h: h.score)
