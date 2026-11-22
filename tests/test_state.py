import json
from datetime import datetime, timedelta, timezone

from dealradar.models import Hit, Listing
from dealradar.state import SeenState


def make_hit(uadid="1", price=300_000, score=70):
    return Hit(
        listing=Listing(uadid=uadid, title=f"Lenovo Legion 5 {uadid}", url="https://x", price=price),
        profile="Legion 5",
        score=score,
    )


def test_new_and_mark(tmp_path):
    state = SeenState(tmp_path / "seen.json")
    state.load()
    assert state.is_new("1")

    state.mark(make_hit("1"))
    assert not state.is_new("1")
    assert len(state) == 1


def test_save_and_reload(tmp_path):
    path = tmp_path / "seen.json"
    state = SeenState(path)
    state.load()
    state.mark(make_hit("42", price=250_000))
    state.save()

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert data["items"]["42"]["price"] == 250_000

    again = SeenState(path)
    again.load()
    assert not again.is_new("42")


def test_price_drop_detection(tmp_path):
    state = SeenState(tmp_path / "seen.json")
    state.load()
    state.mark(make_hit("1", price=400_000))
    assert state.price_drop("1", 350_000, 10) == (400_000, 12.5)
    assert state.price_drop("1", 390_000, 10) is None
    assert state.price_drop("1", 100_000, 0) is None
    assert state.price_drop("ismeretlen", 100_000, 10) is None


def test_prune_old_entries(tmp_path):
    state = SeenState(tmp_path / "seen.json", retention_days=30)
    state.load()
    old = (datetime.now(timezone.utc) - timedelta(days=90)).replace(microsecond=0).isoformat()
    state.items["old"] = {"first_seen": old, "price": 1}
    state.mark(make_hit("new"))
    assert state.prune() == 1
    assert state.is_new("old")
    assert not state.is_new("new")


def test_corrupted_state_is_ignored(tmp_path):
    path = tmp_path / "seen.json"
    path.write_text("{ez nem json", encoding="utf-8")
    state = SeenState(path)
    state.load()
    assert len(state) == 0
