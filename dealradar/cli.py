"""Parancssori belépési pont és a futás vezérlése."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import requests

from .benchmarks import Benchmarks
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


def _ci_error(title: str, message: str) -> None:
    """GitHub Actions annotáció, hogy a hiba okát ne a logban kelljen keresni."""
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::error title={title}::{message}", flush=True)


def _ci_notice(message: str) -> None:
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::notice::{message}", flush=True)


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

    # A deep scan után a leírásban talált tiltott szavak és a képernyőméret
    # is számítanak. A szűrést minden jelöltre alkalmazzuk: ha a méret nem
    # derült ki (mert nem került sorra a deep scanben), az is kiesik.
    result: list[Listing] = []
    for listing in candidates:
        if not any(passes_filters(listing, watch.filters, final=True) for watch in config.watches):
            log.debug("Kiszűrve a leírás/méret alapján: %s", listing.title)
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


def attach_benchmarks(fetcher: Fetcher, hits: list[Hit]) -> None:
    """PassMark CPU Mark / G3D Mark pontszámok a találatokhoz (best effort)."""
    bench = Benchmarks(fetcher)
    for hit in hits:
        specs = hit.listing.specs
        hit.cpu_bench = bench.cpu(specs.cpu)
        hit.gpu_bench = bench.gpu(specs.gpus[0] if specs.gpus else None)
        log.debug(
            "benchmark: %s -> CPU %s, GPU %s",
            hit.listing.title[:40],
            hit.cpu_bench.score if hit.cpu_bench else "nincs",
            hit.gpu_bench.score if hit.gpu_bench else "nincs",
        )


def self_check(config: Config) -> int:
    """Környezet ellenőrzése: konfiguráció, Discord webhook, Hardverapró."""
    problems = 0
    log.info("Önellenőrzés indul")

    log.info(
        "Konfiguráció: %d figyelő, %d profil, min_score=%d",
        len(config.watches),
        len(config.profiles),
        config.settings.min_score,
    )
    _ci_notice(f"Konfiguráció rendben: {len(config.watches)} figyelő, {len(config.profiles)} profil")

    # --- Discord webhook ---
    webhook = config.settings.webhook_url
    if not webhook:
        log.error("A %s környezeti változó nincs beállítva", config.settings.webhook_env)
        _ci_error(
            "Hiányzó webhook secret",
            f"A(z) {config.settings.webhook_env} secret nem érhető el. "
            "Settings -> Secrets and variables -> Actions -> Secrets.",
        )
        problems += 1
    elif not webhook.startswith("https://discord.com/api/webhooks/"):
        log.error("A webhook URL formátuma hibás")
        _ci_error(
            "Hibás webhook URL",
            "A secret értéke nem https://discord.com/api/webhooks/... formátumú.",
        )
        problems += 1
    else:
        try:
            response = requests.get(webhook, timeout=10)
        except requests.RequestException as exc:
            log.error("A Discord nem elérhető: %s", exc)
            _ci_error("Discord nem elérhető", f"Hálózati hiba: {exc}")
            problems += 1
        else:
            if response.status_code == 200:
                data = response.json()
                log.info(
                    "Webhook rendben: %s (csatorna: %s)",
                    data.get("name") or "(névtelen)",
                    data.get("channel_id"),
                )
                _ci_notice("A Discord webhook érvényes")
            else:
                log.error("A webhook ellenőrzése HTTP %s", response.status_code)
                _ci_error(
                    "Érvénytelen webhook",
                    f"A Discord HTTP {response.status_code}-at adott. "
                    "Lehet, hogy törölték vagy újragenerálták.",
                )
                problems += 1

    # --- Hardverapró ---
    fetcher = Fetcher(
        user_agent="apro-deal-radar/1.0 (+https://github.com/Gyuri125/hardverapro-bot)",
        delay=config.settings.request_delay,
        timeout=config.settings.timeout,
        retries=config.settings.retries,
    )
    try:
        html = fetcher.get(config.watches[0].url)
    except FetchError as exc:
        log.error("A Hardverapró nem elérhető: %s", exc)
        _ci_error(
            "Hardverapró nem elérhető",
            f"{exc}. A GitHub runner IP-címét blokkolhatja az oldal, vagy hálózati hiba van.",
        )
        problems += 1
    else:
        found = parse_list_page(html)
        if found:
            log.info("Hardverapró rendben: %d hirdetés az első oldalon", len(found))
            _ci_notice(f"Hardverapró rendben: {len(found)} hirdetés az első oldalon")
        else:
            log.error("Az oldal letöltődött, de nem találtam hirdetést")
            _ci_error(
                "Üres oldal",
                "A Hardverapró válaszolt, de a parser nem talált hirdetést. "
                "Valószínűleg megváltozott a HTML.",
            )
            problems += 1

    if problems:
        log.error("Önellenőrzés: %d probléma", problems)
        return 1

    log.info("Önellenőrzés: minden rendben")
    return 0


def print_table(hits: list[Hit], limit: int = 25) -> None:
    if not hits:
        print("Nincs a pontszám-küszöböt elérő találat.")
        return
    print()
    print(f"{'PONT':>5}  {'ÁR':>13}  {'CPU':>7}  {'PROFIL':<34}  CÍM")
    print("-" * 128)
    for hit in hits[:limit]:
        price = format_huf(hit.listing.price)
        cpu = str(hit.cpu_bench.score) if hit.cpu_bench else "–"
        print(f"{hit.score:5d}  {price:>13}  {cpu:>7}  {hit.profile[:34]:<34}  {hit.listing.title[:56]}")
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
        "--self-check",
        action="store_true",
        help="környezet ellenőrzése (konfiguráció, webhook, Hardverapró), hirdetéskeresés nélkül",
    )
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

    if args.self_check:
        return self_check(config)

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

    if new_hits:
        attach_benchmarks(fetcher, new_hits)

    print_table(hits if args.show_all else new_hits)

    if not webhook:
        if args.dry_run:
            log.warning("Nincs %s környezeti változó – dry-run módban maradunk.", config.settings.webhook_env)
        else:
            raise ConfigError(
                f"Hiányzik a {config.settings.webhook_env} környezeti változó "
                f"(Discord webhook URL). Dry-runhoz add meg a --dry-run kapcsolót."
            )

    sent: set[str] = set()
    if new_hits:
        dry = args.dry_run or not webhook
        sent = send(webhook or "", new_hits, dry_run=dry)
        if not dry:
            for hit in new_hits:
                if hit.listing.uadid in sent:
                    state.mark(hit)

    state.save()
    log.info("Kész. Elküldve: %d, state mérete: %d", len(sent), len(state))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except (ConfigError, FetchError) as exc:
        log.error("%s", exc)
        _ci_error("Hiba", str(exc))
        return 1
    except RuntimeError as exc:
        # pl. Discord hiba / rate limit
        log.error("%s", exc)
        _ci_error("Hiba", str(exc))
        return 1
    except KeyboardInterrupt:  # pragma: no cover
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
