"""A helyi .env betöltő tesztjei."""

import os

from dealradar.config import load_dotenv


def test_loads_values(tmp_path, monkeypatch):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("MASIK", raising=False)
    path = tmp_path / ".env"
    path.write_text(
        "# komment\n"
        "\n"
        'DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/1/abc"\n'
        "MASIK=ertek \n"
        "EZ_NEM_ERVENYES_SOR\n",
        encoding="utf-8",
    )
    assert load_dotenv(path) is True
    assert os.environ["DISCORD_WEBHOOK_URL"] == "https://discord.com/api/webhooks/1/abc"
    assert os.environ["MASIK"] == "ertek"


def test_does_not_override_real_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://valodi")
    path = tmp_path / ".env"
    path.write_text("DISCORD_WEBHOOK_URL=https://fajlbol\n", encoding="utf-8")
    load_dotenv(path)
    assert os.environ["DISCORD_WEBHOOK_URL"] == "https://valodi"


def test_missing_file_is_not_an_error(tmp_path):
    assert load_dotenv(tmp_path / "nincs.env") is False


def test_empty_value_is_treated_as_unset(tmp_path, monkeypatch):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    path = tmp_path / ".env"
    path.write_text("DISCORD_WEBHOOK_URL=\n", encoding="utf-8")
    load_dotenv(path)
    assert os.environ.get("DISCORD_WEBHOOK_URL") == ""
