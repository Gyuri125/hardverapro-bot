"""Parancssori belépési pont és a futás vezérlése."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import Config, ConfigError, load_config, load_dotenv
from .fetch import FetchError, Fetcher
from .models import Hit, Listing
from .notify import format_huf, send, send_test
from .parse import enrich, page_url, parse_detail_page, parse_list_page
from .rules import best_hit, compute_market_medians, passes_filters
from .specs import extract
from .state import SeenState

log = logging.getLogger("dealradar")


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )


# --------------------------------------------------------------------------
#  begyűjtés
# --------------------------------------------------------------------------


def collect(config: Config, fetcher: Fetcher, *, cache: bool, max_pages: int | None = None) -> list[Listing]:
    listings: dict[str, Listing] = {}
    failed = 0

    for watch in config.watches:
        pages = max_pages or watch.max_pages
        for page_index in range(pages):
            url = page_url(watch.url, page_index)
            try:
                html = fetcher.get(url, use_cache=cache)
            except FetchError as exc:
                failed += 1
                log.error("Nem sikerült letölteni: %s (%s)", url, exc)
                break
            found = parse_list_page(html, url)
            log.info("%s – %d. oldal: %d hirdetés", watch.name, page_index + 1, len(found))
            for listing in found:
                listing.specs = extract(listing.text, listing.title)
                listings.setdefault(listing.uadid, listing)

    if failed and not listings:
        raise FetchError("Egyetlen oldalt sem sikerült letölteni.")

    return list(listings.values())


# --------------------------------------------------------------------------
#  feldolgozás
# --------------------------------------------------------------------------


def prepare(
    config: Config,
    fetcher: Fetcher,
    listings: list[Listing],
    *,
    cache: bool,
) -> list[Listing]:
    """Watch szűrők + opcionális részoldal-letöltés (deep scan)."""
    candidates: list[Listing] = []
    seen_urls: set[str] = set()

    for watch in config.watches:
        for listing in listings:
            if listing.uadid in seen_urls:
                continue
            if passes_filters(listing, watch.filters):
                seen_urls.add(listing.uadid)
                candidates.append(listing)

    if not config.settings.deep_scan or not candidates:
        return candidates

    # Csak azokat a jelölteket töltjük le, amelyek vagy illeszkednek valamelyik
    # profilra, vagy a címből nem derült ki a GPU (lehet, hogy a leírásban van).
    interesting = [
        c
        for c in candidates
        if best_hit(c, config.profiles, config.market, {}) is not None or not c.specs.gpus
    ]
    interesting.sort(key=lambda c: c.price or 0)
    batch = interesting[: config.settings.deep_scan_limit]

    if batch:
        log.info("Részoldalak letöltése: %d db", len(batch))
    enriched: dict[str, Listing] = {}
    for listing in batch:
        try:
            html = fetcher.get(listing.url_abs, use_cache=cache)
        except FetchError as exc:
            log.warning("Részoldal kihagyva (%s): %s", listing.url_abs, exc)
            continue
        detail = parse_detail_page(html)
        enrich(listing, detail)
        listing.specs = extract(listing.text, listing.title)
        enriched[listing.uadid] = listing

    # A deep scan után a leírásban talált tiltott szavak is számíthatnak.
    result: list[Listing] = []
    for listing in candidates:
        if listing.uadid in enriched:
            if not any(passes_filters(listing, watch.filters) for watch in config.watches):
                log.debug("Kiszűrve a leírás alapján: %s", listing.title)
                continue
        result.append(listing)
    return result


def evaluate(config: Config, listings: list[Listing]) -> list[Hit]:
    medians = compute_market_medians(listings, config.market)
    if medians:
        log.info("Piaci medián csoportok: %s", ", ".join(f"{k}={format_huf(v)}" for k, v in sorted(medians.items())))

    hits: list[Hit] = []
    for listing in listings:
        hit = best_hit(listing, config.profiles, config.market, medians)
        if hit and hit.score >= config.settings.min_score:
            hits.append(hit)

    hits.sort(key=lambda h: (-h.score, h.listing.price or 0))
    return hits


# --------------------------------------------------------------------------
#  kimenet
# --------------------------------------------------------------------------


def print_table(hits: list[Hit], limit: int = 25) -> None:
    if not hits:
        print("Nincs a pontszám-küszöböt elérő találat.")
        return
    print()
    print(f"{'PONT':>5}  {'ÁR':>13}  {'PROFIL':<34}  CÍM")
    print("-" * 120)
    for hit in hits[:limit]:
        price = format_huf(hit.listing.price)
        print(f"{hit.score:5d}  {price:>13}  {hit.profile[:34]:<34}  {hit.listing.title[:60]}")
    if len(hits) > limit:
        print(f"... és további {len(hits) - limit} találat")
    print()


# --------------------------------------------------------------------------
#  main
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dealradar",
        description="Hardverapró deal radar – jó használt laptopok keresése és Discord értesítés.",
    )
    parser.add_argument("--config", default="config.yaml", help="a YAML konfiguráció (alap: config.yaml)")
    parser.add_argument("--dry-run", action="store_true", help="ne küldjön Discordra, csak listázza")
    parser.add_argument("--cache", action="store_true", help="a letöltött oldalak cache-elése a .cache mappába")
    parser.add_argument("--max-pages", type=int, default=None, help="oldalak felülírása figyelőnként")
    parser.add_argument("--watch", default=None, help="csak azok a figyelők, amelyek nevében szerepel ez a szöveg")
    parser.add_argument("--show-all", action="store_true", help="az összes találat kiírása a küszöb alattiakkal együtt")
    parser.add_argument(
        "--test-webhook",
        action="store_true",
        help="csak egy tesztüzenetet küld a Discord webhookra, majd kilép",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="részletes napló")
    return parser


def run(args: argparse.Namespace) -> int:
    _setup_logging(args.verbose)

    # Helyi fejlesztéshez: a .env fájlból is beolvassa a webhookot.
    # GitHubon nincs .env, ott a Secretből jön.
    if load_dotenv():
        log.debug(".env betöltve")

    config = load_config(args.config)

    webhook = config.settings.webhook_url
    if args.test_webhook:
        if not webhook and not args.dry_run:
            raise ConfigError(f"Hiányzik a {config.settings.webhook_env} környezeti változó.")
        if webhook:
            send_test(webhook, dry_run=args.dry_run)
            log.info("Teszt üzenet elküldve.")
        return 0

    if args.watch:
        needle = args.watch.lower()
        available = [w.name for w in config.watches]
        config.watches = [w for w in config.watches if needle in w.name.lower()]
        if not config.watches:
            raise ConfigError(f"Nincs '{args.watch}' nevű figyelő. Elérhetők: {available}")

    cache_dir = Path(".cache") if args.cache else None
    fetcher = Fetcher(
        user_agent="apro-deal-radar/1.0 (+https://github.com/)",
        delay=config.settings.request_delay,
        timeout=config.settings.timeout,
        retries=config.settings.retries,
        cache_dir=cache_dir,
    )

    state = SeenState(config.settings.state_file, config.settings.state_retention_days)
    state.load()
    removed = state.prune()
    if removed:
        log.info("State: %d régi bejegyzés törölve", removed)

    log.info("Indulás: %d figyelő, %d profil", len(config.watches), len(config.profiles))
    listings = collect(config, fetcher, cache=args.cache, max_pages=args.max_pages)
    log.info("Összes egyedi hirdetés: %d", len(listings))

    candidates = prepare(config, fetcher, listings, cache=args.cache)
    log.info("Szűrők után: %d", len(candidates))

    hits = evaluate(config, candidates)
    log.info("Küszöb feletti találat: %d", len(hits))

    new_hits: list[Hit] = []
    for hit in hits:
        uadid = hit.listing.uadid
        if state.is_new(uadid) or state.price_dropped(
            uadid, hit.listing.price, config.settings.renotify_price_drop_percent
        ):
            new_hits.append(hit)

    skipped = len(hits) - len(new_hits)
    if skipped:
        log.info("%d találat már ismert, kihagyva", skipped)

    new_hits = new_hits[: config.settings.max_notifications]
    print_table(hits if args.show_all else new_hits)

    if not webhook:
        if args.dry_run:
            log.warning("Nincs %s környezeti változó – dry-run módban maradunk.", config.settings.webhook_env)
        else:
            raise ConfigError(
                f"Hiányzik a {config.settings.webhook_env} környezeti változó "
                f"(Discord webhook URL). Dry-runhoz add meg a --dry-run kapcsolót."
            )

    sent = 0
    if new_hits:
        dry = args.dry_run or not webhook
        sent = send(webhook or "", new_hits, dry_run=dry)
        if not dry:
            for hit in new_hits:
                state.mark(hit)

    state.save()
    log.info("Kész. Elküldve: %d, state mérete: %d", sent, len(state))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except (ConfigError, FetchError) as exc:
        log.error("%s", exc)
        return 1
    except RuntimeError as exc:
        # pl. Discord hiba / rate limit
        log.error("%s", exc)
        return 1
    except KeyboardInterrupt:  # pragma: no cover
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
