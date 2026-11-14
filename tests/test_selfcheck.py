"""Az önellenőrző mód tesztjei (hálózat nélkül)."""

from pathlib import Path

from dealradar import cli
from dealradar.config import load_config

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = (ROOT / "tests" / "fixtures" / "list_page.html").read_text(encoding="utf-8")


class StubFetcher:
    def __init__(self, *args, **kwargs):
        pass

    def get(self, url, use_cache=False):
        return FIXTURE


class StubResponse:
    status_code = 200

    def json(self):
        return {"name": "teszt webhook", "channel_id": "123"}


class ErrorResponse:
    status_code = 404

    def json(self):
        return {}


def make_config():
    return load_config(ROOT / "config.yaml")


def test_self_check_ok(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/1/abc")
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setattr(cli, "Fetcher", StubFetcher)
    monkeypatch.setattr(cli.requests, "get", lambda *a, **k: StubResponse())
    assert cli.self_check(make_config()) == 0


def test_self_check_missing_webhook(monkeypatch):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setattr(cli, "Fetcher", StubFetcher)
    assert cli.self_check(make_config()) == 1


def test_self_check_invalid_webhook_format(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://pelda.hu/nem-webhook")
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setattr(cli, "Fetcher", StubFetcher)
    assert cli.self_check(make_config()) == 1


def test_self_check_deleted_webhook(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/1/abc")
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setattr(cli, "Fetcher", StubFetcher)
    monkeypatch.setattr(cli.requests, "get", lambda *a, **k: ErrorResponse())
    assert cli.self_check(make_config()) == 1


def test_self_check_site_unreachable(monkeypatch):
    from dealradar.fetch import FetchError

    class BrokenFetcher(StubFetcher):
        def get(self, url, use_cache=False):
            raise FetchError("HTTP 403")

    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/1/abc")
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setattr(cli, "Fetcher", BrokenFetcher)
    monkeypatch.setattr(cli.requests, "get", lambda *a, **k: StubResponse())
    assert cli.self_check(make_config()) == 1


def test_ci_error_annotation_is_emitted(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    cli._ci_error("Teszt hiba", "valami baj van")
    out = capsys.readouterr().out
    assert out.startswith("::error title=Teszt hiba::")
    assert "valami baj van" in out
