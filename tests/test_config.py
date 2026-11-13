from pathlib import Path

import pytest
import yaml

from dealradar.config import ConfigError, load_config

ROOT = Path(__file__).resolve().parent.parent


def test_project_config_is_valid():
    config = load_config(ROOT / "config.yaml")
    assert len(config.watches) >= 1
    assert len(config.profiles) >= 1
    assert config.settings.min_score > 0
    assert config.market.group_by in {"gpu", "cpu", "brand"}
    assert len(config.profile_names()) == len(set(config.profile_names()))


def test_missing_file_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "nincs.yaml")


def test_empty_config_raises(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("watches: []\nprofiles: []\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path)


def test_profile_without_matchers_raises(tmp_path):
    path = tmp_path / "config.yaml"
    data = {
        "watches": [{"name": "x", "url": "https://hardverapro.hu/aprok/notebook/index.html"}],
        "profiles": [{"name": "üres profil", "max_price": 100000}],
    }
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path)


def test_bad_price_range_raises(tmp_path):
    path = tmp_path / "config.yaml"
    data = {
        "watches": [{"name": "x", "url": "https://hardverapro.hu/aprok/notebook/index.html"}],
        "profiles": [
            {"name": "p", "any_keywords": ["legion"], "min_price": 500000, "max_price": 100000}
        ],
    }
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path)


def test_watch_filters_override_global(tmp_path):
    path = tmp_path / "config.yaml"
    data = {
        "filters": {"max_price": 100000},
        "watches": [
            {"name": "global", "url": "https://hardverapro.hu/aprok/notebook/index.html"},
            {"name": "sajat", "url": "https://hardverapro.hu/aprok/notebook/index.html",
             "filters": {"max_price": 500000}},
        ],
        "profiles": [{"name": "p", "any_keywords": ["legion"]}],
    }
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    config = load_config(path)
    assert config.watches[0].filters.max_price == 100000
    assert config.watches[1].filters.max_price == 500000
