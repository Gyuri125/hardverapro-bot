"""Látott hirdetések nyilvántartása (duplikátum-szűrés)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import Hit

log = logging.getLogger(__name__)

VERSION = 1


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


class SeenState:
    """JSON fájlban tárolt állapot.

    GitHub Actionsben ez a fájl a repóba visszakommitolva marad meg
    futások között (a runner minden alkalommal tiszta).
    """

    def __init__(self, path: str | Path, retention_days: int = 60) -> None:
        self.path = Path(path)
        self.retention_days = retention_days
        self.items: dict[str, dict] = {}
        self.meta: dict = {}
        self.dirty = False

    # ------------------------------------------------------------------
    def load(self) -> None:
        if not self.path.exists():
            self.items = {}
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Nem sikerült beolvasni a state fájlt (%s): %s", self.path, exc)
            self.items = {}
            return
        items = data.get("items") if isinstance(data, dict) else None
        self.items = items if isinstance(items, dict) else {}
        meta = data.get("meta") if isinstance(data, dict) else None
        self.meta = meta if isinstance(meta, dict) else {}

    def save(self) -> None:
        if not self.dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": VERSION,
            "updated_at": _iso(_now()),
            "meta": self.meta,
            "items": self.items,
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self.dirty = False

    # ------------------------------------------------------------------
    def prune(self) -> int:
        cutoff = _now() - timedelta(days=self.retention_days)
        removed = 0
        for uadid, entry in list(self.items.items()):
            first_seen = _parse(entry.get("first_seen"))
            if first_seen and first_seen < cutoff:
                del self.items[uadid]
                removed += 1
        if removed:
            self.dirty = True
        return removed

    def is_new(self, uadid: str) -> bool:
        return uadid not in self.items

    def previous_price(self, uadid: str) -> int | None:
        value = self.items.get(uadid, {}).get("price")
        return value if isinstance(value, int) and value > 0 else None

    def price_drop(
        self, uadid: str, price: int | None, percent: int
    ) -> tuple[int, float] | None:
        """Ha az ár jelentősen lecsökkent: (régi ár, csökkenés %-ban)."""
        if percent <= 0 or price is None:
            return None
        old = self.previous_price(uadid)
        if old is None:
            return None
        if price <= old * (1 - percent / 100):
            return old, (old - price) / old * 100.0
        return None

    def mark(self, hit: Hit) -> None:
        uadid = hit.listing.uadid
        now = _iso(_now())
        entry = self.items.get(uadid, {})
        self.items[uadid] = {
            "first_seen": entry.get("first_seen", now),
            "notified_at": now,
            "price": hit.listing.price,
            "profile": hit.profile,
            "score": hit.score,
            "title": hit.listing.title[:200],
            "url": hit.listing.url_abs,
        }
        self.dirty = True

    def __len__(self) -> int:
        return len(self.items)
