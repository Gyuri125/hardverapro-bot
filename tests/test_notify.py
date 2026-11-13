from dealradar.models import Hit, Listing
from dealradar.notify import build_embed, format_huf, send


def make_hit(score=80, price=300_000):
    listing = Listing(
        uadid="1",
        title="Lenovo Legion 5 15ACH6H / Ryzen 7 5800H / 16GB / 512GB / RTX 3060 " * 6,
        url="https://hardverapro.hu/apro/teszt/friss.html",
        price=price,
        seller="Teszt Elek",
        seller_rating=22,
        location="Budapest",
        posted="ma 12:44",
        shipping=True,
        condition="használt",
    )
    return Hit(listing=listing, profile="Legion 5", score=score, reasons=["16 GB RAM"], target_price=340_000)


def test_format_huf():
    assert format_huf(400_000) == "400 000 Ft"
    assert format_huf(None) == "–"


def test_build_embed_limits():
    hit = make_hit()
    embed = build_embed(hit)
    assert len(embed["title"]) <= 256
    assert embed["url"].startswith("https://")
    assert embed["color"] == 0x2ECC71
    for field in embed["fields"]:
        assert len(field["name"]) <= 256
        assert len(field["value"]) <= 1024


def test_colors_by_score():
    assert build_embed(make_hit(score=90))["color"] == 0x2ECC71
    assert build_embed(make_hit(score=65))["color"] == 0xF1C40F
    assert build_embed(make_hit(score=50))["color"] == 0xE67E22


def test_dry_run_does_not_send(capsys):
    sent = send("https://pelda.invalid/webhook", [make_hit()], dry_run=True)
    assert sent == 0
    output = capsys.readouterr().out
    assert "[DRY]" in output
    assert "hardverapro.hu" in output


def test_empty_hits():
    assert send("https://pelda.invalid/webhook", [], dry_run=False) == 0
