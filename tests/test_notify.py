"""Discord embed: linkek, benchmark pontok, billentyűzet-figyelmeztetés."""

from dealradar.benchmarks import BenchResult
from dealradar.models import Hit, Listing
from dealradar.notify import build_embed, format_huf, send
from dealradar.specs import extract

TEXT = (
    "Lenovo Legion 5 15ACH6H RTX 4060 i7-14700HX 32 GB DDR5 RAM 1 TB NVMe SSD "
    "165 Hz OLED panel, garancia 2028-ig"
)


def make_hit(keyboard=None) -> Hit:
    listing = Listing(
        uadid="1",
        title="Eladó Lenovo Legion 5 15ACH6H gamer laptop",
        url="https://hardverapro.hu/apro/teszt/friss.html",
        price=350_000,
        seller="Teszt Elek",
        seller_rating=22,
        location="Budapest",
        posted="ma 12:44",
        shipping=True,
        condition="használt",
    )
    listing.specs = extract(TEXT)
    listing.specs.keyboard = keyboard
    return Hit(listing=listing, profile="Sweet spot", score=80, target_price=390_000)


def fields_of(embed) -> dict[str, str]:
    return {field["name"]: field["value"] for field in embed["fields"]}


def test_cpu_field_links_to_manufacturer_and_shows_score():
    hit = make_hit()
    hit.cpu_bench = BenchResult("Intel Core i7-14700HX", 36314, "https://www.cpubenchmark.net/x", "cpu")
    embed = build_embed(hit)
    value = fields_of(embed)["Processzor"]
    assert "](https://www.intel.com/" in value
    assert "36 314" in value
    assert "i7-14700HX" in value


def test_gpu_field_links_to_passmark():
    hit = make_hit()
    hit.gpu_bench = BenchResult("GeForce RTX 4060 Laptop GPU", 17306, "https://www.videocardbenchmark.net/g", "gpu")
    value = fields_of(build_embed(hit))["Videokártya"]
    assert "](https://www.videocardbenchmark.net/g)" in value
    assert "17 306" in value
    assert "RTX 4060" in value


def test_unknown_keyboard_is_highlighted():
    value = fields_of(build_embed(make_hit()))["Billentyűzet"]
    assert "nem derül ki" in value
    assert "kérdezz" in value.lower()


def test_hungarian_keyboard_is_confirmed():
    assert fields_of(build_embed(make_hit(keyboard="hu")))["Billentyűzet"] == "magyar (a hirdetés szerint)"


def test_specs_link_present():
    value = fields_of(build_embed(make_hit()))["Specifikáció"]
    assert value.startswith("[Megnézem](https://www.google.com/search?q=")


def test_embed_respects_discord_limits():
    embed = build_embed(make_hit())
    assert len(embed["title"]) <= 256
    assert len(embed["description"]) <= 4096
    for field in embed["fields"]:
        assert len(field["name"]) <= 256
        assert len(field["value"]) <= 1024
    assert len(embed["fields"]) <= 25


def test_embed_has_no_raw_newlines_issue():
    embed = build_embed(make_hit())
    assert "\n" not in embed["title"]
    assert "\n" not in embed["footer"]["text"]


# --- alap működés ---------------------------------------------------------


def test_format_huf():
    assert format_huf(400_000) == "400 000 Ft"
    assert format_huf(None) == "–"


def test_colors_by_score():
    assert build_embed(make_hit())["color"] == 0x2ECC71
    hit = make_hit()
    hit.score = 65
    assert build_embed(hit)["color"] == 0xF1C40F
    hit.score = 50
    assert build_embed(hit)["color"] == 0xE67E22


def test_dry_run_does_not_send(capsys):
    sent = send("https://pelda.invalid/webhook", [make_hit()], dry_run=True)
    assert sent == 0
    output = capsys.readouterr().out
    assert "[DRY]" in output
    assert "hardverapro.hu" in output


def test_empty_hits():
    assert send("https://pelda.invalid/webhook", [], dry_run=False) == 0
