import pytest

from dealradar.config import MarketCompare, Profile, ProfileSpecs, WatchedFilters
from dealradar.models import Listing
from dealradar.rules import (
    best_hit,
    compute_market_medians,
    match_profile,
    passes_filters,
    score,
)
from dealradar.specs import extract


def make_listing(title: str, price: int | None = 300_000, **kwargs) -> Listing:
    listing = Listing(
        uadid=kwargs.pop("uadid", "123"),
        title=title,
        url="https://hardverapro.hu/apro/teszt/friss.html",
        price=price,
        **kwargs,
    )
    listing.specs = extract(title)
    return listing


LEGION = Profile(
    name="Legion 5",
    any_keywords=["legion 5"],
    max_price=430_000,
    deal_price=340_000,
    specs=ProfileSpecs(gpu_any=["4060", "4070"], min_ram_gb=16, min_storage_gb=512),
)


# --------------------------------------------------------------------------
#  watch szűrők
# --------------------------------------------------------------------------


def test_price_range_filter():
    filters = WatchedFilters(min_price=100_000, max_price=500_000)
    assert passes_filters(make_listing("Lenovo Legion 5", 300_000), filters)
    assert not passes_filters(make_listing("Lenovo Legion 5", 90_000), filters)
    assert not passes_filters(make_listing("Lenovo Legion 5", 900_000), filters)
    assert not passes_filters(make_listing("Lenovo Legion 5", None), filters)


def test_exclude_keywords_are_accent_insensitive():
    filters = WatchedFilters(exclude_keywords=["hibás", "törött"])
    assert not passes_filters(make_listing("Lenovo Legion 5 HIBAS kijelzo"), filters)
    assert not passes_filters(make_listing("Legion 5 torott sarok"), filters)
    assert passes_filters(make_listing("Lenovo Legion 5 tokeletes"), filters)


def test_promoted_and_business_filters():
    filters = WatchedFilters(exclude_promoted=True, allow_business=False)
    assert not passes_filters(make_listing("Legion 5", promoted=True), filters)
    assert not passes_filters(make_listing("Legion 5", is_business=True), filters)
    assert passes_filters(make_listing("Legion 5"), filters)


def test_seller_rating_and_location():
    filters = WatchedFilters(min_seller_rating=10, locations=["budapest"])
    assert not passes_filters(make_listing("Legion 5", seller_rating=2, location="Budapest"), filters)
    assert passes_filters(make_listing("Legion 5", seller_rating=50, location="Budapest, XI. ker."), filters)
    assert not passes_filters(make_listing("Legion 5", seller_rating=50, location="Debrecen"), filters)


def test_wanted_ads_are_skipped():
    assert not passes_filters(make_listing("Legion 5", intent="keres"), WatchedFilters())


# --------------------------------------------------------------------------
#  profil illesztés
# --------------------------------------------------------------------------


def test_profile_matches_good_listing():
    listing = make_listing("Lenovo Legion 5 15ACH6H RTX 4060 32GB 1TB", 350_000)
    matched, reasons = match_profile(listing, LEGION)
    assert matched
    assert reasons


def test_profile_rejects_too_expensive():
    listing = make_listing("Lenovo Legion 5 RTX 4060 32GB 1TB", 500_000)
    assert not match_profile(listing, LEGION)[0]


def test_profile_rejects_wrong_gpu():
    listing = make_listing("Lenovo Legion 5 RTX 3050 32GB 1TB", 300_000)
    assert not match_profile(listing, LEGION)[0]


def test_profile_rejects_low_ram():
    listing = make_listing("Lenovo Legion 5 RTX 4060 8GB 512GB", 300_000)
    assert not match_profile(listing, LEGION)[0]


def test_profile_ignores_unknown_ram():
    """Ha a RAM nem derül ki, nem utasítjuk el a hirdetést."""
    listing = make_listing("Lenovo Legion 5 RTX 4060 1TB", 300_000)
    assert match_profile(listing, LEGION)[0]


def test_profile_rejects_other_model():
    listing = make_listing("Asus ROG Strix RTX 4060 32GB 1TB", 300_000)
    assert not match_profile(listing, LEGION)[0]


# --------------------------------------------------------------------------
#  pontozás
# --------------------------------------------------------------------------


def test_cheaper_scores_higher():
    compare = MarketCompare(enabled=False)
    cheap = make_listing("Lenovo Legion 5 RTX 4060 32GB 1TB", 280_000, uadid="1")
    pricey = make_listing("Lenovo Legion 5 RTX 4060 32GB 1TB", 420_000, uadid="2")
    cheap_hit = score(cheap, LEGION, compare, None)
    pricey_hit = score(pricey, LEGION, compare, None)
    assert cheap_hit and pricey_hit
    assert cheap_hit.score > pricey_hit.score
    assert 0 <= pricey_hit.score <= 100 and 0 <= cheap_hit.score <= 100


def test_score_is_clamped_and_has_target():
    compare = MarketCompare(enabled=False)
    hit = score(make_listing("Lenovo Legion 5 RTX 4060 32GB 1TB", 200_000), LEGION, compare, None)
    assert hit is not None
    assert hit.target_price == 340_000
    assert hit.score <= 100


def test_score_adds_market_reason():
    compare = MarketCompare(enabled=True, min_samples=2, good_deal_discount=0.20)
    listing = make_listing("Lenovo Legion 5 RTX 4060 32GB 1TB", 250_000)
    hit = score(listing, LEGION, compare, median=400_000)
    assert hit is not None
    assert any("medián" in reason for reason in hit.reasons)


# --------------------------------------------------------------------------
#  piaci medián
# --------------------------------------------------------------------------


def test_market_medians_need_enough_samples():
    compare = MarketCompare(enabled=True, group_by="gpu", min_samples=3)
    listings = [
        make_listing("Lenovo Legion 5 RTX 4060 16GB", price, uadid=str(i))
        for i, price in enumerate([300_000, 400_000, 500_000])
    ]
    medians = compute_market_medians(listings, compare)
    assert medians["rtx 4060"] == 400_000

    few = listings[:2]
    assert compute_market_medians(few, compare) == {}


def test_best_hit_picks_highest_score():
    compare = MarketCompare(enabled=False)
    listing = make_listing("Lenovo Legion 5 RTX 4060 32GB 1TB", 250_000)
    strict = Profile(name="strict", any_keywords=["legion"], max_price=260_000, deal_price=200_000)
    generous = Profile(name="generous", any_keywords=["legion"], max_price=400_000, deal_price=380_000)
    hit = best_hit(listing, [strict, generous], compare, {})
    assert hit is not None
    assert hit.profile == "generous"
