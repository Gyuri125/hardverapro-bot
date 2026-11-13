"""Specifikáció-felismerés pontossági tesztjei (bővíthető csapdák, strict profil)."""

from dealradar.config import Profile, ProfileSpecs
from dealradar.models import Listing
from dealradar.rules import match_profile
from dealradar.specs import extract


def test_expandable_ram_is_not_mistaken_for_actual():
    specs = extract("Memória: bővíthető max 32 GB RAM-ig, alapból 16 GB DDR4")
    assert specs.ram_gb == 16


def test_expandable_storage_is_not_mistaken_for_actual():
    specs = extract("Háttértár: 512 GB SSD, bővíthető 2 TB-ig")
    assert specs.storage_gb == 512


def test_expandable_only_gives_none():
    assert extract("maximum 32 GB RAM-ig bővíthető").ram_gb is None
    assert extract("bővíthető 1 TB-ig").storage_gb is None


def test_plain_values_still_work():
    assert extract("32 GB DDR5 RAM, 1 TB NVMe SSD").ram_gb == 32
    assert extract("32 GB DDR5 RAM, 1 TB NVMe SSD").storage_gb == 1024


def make_listing(text: str, price: int = 250_000) -> Listing:
    listing = Listing(uadid="1", title=text, url="https://x", price=price)
    listing.specs = extract(text)
    return listing


STRICT = Profile(
    name="Üzleti érték",
    max_price=320_000,
    specs=ProfileSpecs(min_ram_gb=32, min_storage_gb=1024, strict=True),
)

LOOSE = Profile(
    name="Laza",
    max_price=320_000,
    specs=ProfileSpecs(min_ram_gb=32, min_storage_gb=1024, strict=False),
)


def test_strict_profile_rejects_unknown_specs():
    listing = make_listing("Eladó laptop core i5, szép állapot")
    assert listing.specs.ram_gb is None
    assert not match_profile(listing, STRICT)[0]
    # laza módban az ismeretlen átmegy
    assert match_profile(listing, LOOSE)[0]


def test_strict_profile_accepts_known_specs():
    listing = make_listing("Lenovo ThinkPad 32 GB RAM 1 TB SSD", 250_000)
    assert match_profile(listing, STRICT)[0]


def test_strict_profile_rejects_smaller_specs():
    listing = make_listing("Lenovo ThinkPad 16 GB RAM 512 GB SSD", 250_000)
    assert not match_profile(listing, STRICT)[0]
