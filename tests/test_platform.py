"""Platformkor (CPU-év), memóriageneráció és összehasonlítás tesztjei."""

from dealradar.config import WatchedFilters
from dealradar.models import Listing
from dealradar.rules import passes_filters
from dealradar.specs import extract


# --------------------------------------------------------------------------
#  DDR generáció
# --------------------------------------------------------------------------


def test_memory_generation():
    assert extract("32 GB DDR5 RAM").memory_gen == 5
    assert extract("16GB DDR4 3200MHz").memory_gen == 4
    assert extract("LPDDR5X 32GB").memory_gen == 5
    assert extract("16G D5 / 512G").memory_gen == 5
    assert extract("32G D4 3200").memory_gen == 4
    assert extract("32 GB RAM").memory_gen is None


# --------------------------------------------------------------------------
#  CPU kora
# --------------------------------------------------------------------------


def test_intel_generations():
    assert extract("i5-1135G7").cpu_year == 2021
    assert extract("i7-1165G7").cpu_year == 2021
    assert extract("i7-12700H").cpu_year == 2022
    assert extract("i5-1240P").cpu_year == 2022
    assert extract("i7-13620H").cpu_year == 2023
    assert extract("i9-14900HX").cpu_year == 2024
    assert extract("i5-8250U").cpu_year == 2018


def test_core_ultra_years():
    assert extract("Core Ultra 7 155H").cpu_year == 2024
    assert extract("Core Ultra 7 265H").cpu_year == 2025


def test_amd_ryzen_years():
    assert extract("Ryzen 5 5600H").cpu_year == 2021
    assert extract("Ryzen 7 5800H").cpu_year == 2021
    assert extract("Ryzen 7 7840HS").cpu_year == 2023
    assert extract("Ryzen 7 260").cpu_year == 2024
    assert extract("Ryzen AI 9 365").cpu_year == 2025


def test_unknown_cpu_year():
    assert extract("Intel Pentium N5000").cpu_year is None
    assert extract("valami gép").cpu_year is None


# --------------------------------------------------------------------------
#  szűrők
# --------------------------------------------------------------------------


def make_listing(text: str) -> Listing:
    listing = Listing(uadid="1", title=text, url="https://x", price=300_000)
    listing.specs = extract(text)
    return listing


def test_old_platform_is_rejected():
    filters = WatchedFilters(min_cpu_year=2022, min_memory_gen=5)
    assert not passes_filters(make_listing("Lenovo IdeaPad i5-1135G7 16GB"), filters)
    assert not passes_filters(make_listing("Lenovo IdeaPad i7-1165G7 16GB"), filters)
    assert not passes_filters(make_listing("Acer Nitro Ryzen 5 5600H 16GB"), filters)


def test_new_platform_is_accepted():
    filters = WatchedFilters(min_cpu_year=2022, min_memory_gen=5)
    assert passes_filters(make_listing("Lenovo Legion i7-12700H 16GB DDR5"), filters)
    assert passes_filters(make_listing("ASUS TUF Ryzen 7 7840HS 16GB DDR5"), filters)
    assert passes_filters(make_listing("MSI Cyborg Ultra 7 155H 16GB DDR5"), filters)


def test_ddr4_is_rejected_even_with_new_cpu():
    filters = WatchedFilters(min_cpu_year=2022, min_memory_gen=5)
    assert not passes_filters(make_listing("Lenovo Legion i7-12700H 16GB DDR4 3200"), filters)


def test_unknown_platform_policy():
    filters_allow = WatchedFilters(min_cpu_year=2022, cpu_year_unknown="allow")
    filters_reject = WatchedFilters(min_cpu_year=2022, cpu_year_unknown="reject")

    listing = make_listing("Lenovo Legion 5 16GB DDR5 165Hz")
    assert listing.specs.cpu_year is None

    assert passes_filters(listing, filters_allow)
    assert not passes_filters(listing, filters_reject, final=True)


def test_old_platform_penalty_not_applied_when_disabled():
    filters = WatchedFilters()
    assert passes_filters(make_listing("Lenovo IdeaPad i5-1135G7 16GB DDR4"), filters)
