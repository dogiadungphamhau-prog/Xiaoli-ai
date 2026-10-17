"""Bước 1: đọc và kiểm tra file cấu hình models.yaml."""
import copy
from pathlib import Path

import pytest
import yaml

from app.config import CATEGORIES, ConfigError, load_config

SHIPPED = Path(__file__).resolve().parents[2] / "config" / "models.yaml"

BASE = {
    "timeout_seconds": 8,
    "daily_limit": 30,
    "ip_daily_limit": 90,
    "max_prompt_chars": 4000,
    "max_response_chars": 8000,
    "long_prompt_chars": 1500,
    "models": {"m1": {"provider": "gemini", "model": "x", "label": "M1"}},
    "routes": {c: ["m1"] for c in CATEGORIES},
}


def write(tmp_path, data):
    p = tmp_path / "models.yaml"
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    return p


def test_loads_shipped_config():
    cfg = load_config(SHIPPED)
    assert cfg.timeout_seconds == 8
    assert set(cfg.routes) == set(CATEGORIES)
    for ids in cfg.routes.values():
        assert all(i in cfg.models for i in ids)


def test_loads_valid_custom_config(tmp_path):
    cfg = load_config(write(tmp_path, BASE))
    assert cfg.models["m1"].provider == "gemini"
    assert cfg.models["m1"].label == "M1"


def test_missing_file_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "khong_co.yaml")


def test_unknown_model_in_route_raises(tmp_path):
    d = copy.deepcopy(BASE)
    d["routes"]["code"] = ["khong_ton_tai"]
    with pytest.raises(ConfigError, match="khong_ton_tai"):
        load_config(write(tmp_path, d))


def test_missing_category_raises(tmp_path):
    d = copy.deepcopy(BASE)
    del d["routes"]["math"]
    with pytest.raises(ConfigError, match="math"):
        load_config(write(tmp_path, d))


def test_unknown_provider_raises(tmp_path):
    d = copy.deepcopy(BASE)
    d["models"]["m1"]["provider"] = "abc"
    with pytest.raises(ConfigError, match="abc"):
        load_config(write(tmp_path, d))


@pytest.mark.parametrize("key", ["timeout_seconds", "daily_limit", "ip_daily_limit",
                                 "max_prompt_chars", "max_response_chars", "long_prompt_chars"])
def test_non_positive_setting_raises(tmp_path, key):
    d = copy.deepcopy(BASE)
    d[key] = 0
    with pytest.raises(ConfigError, match=key):
        load_config(write(tmp_path, d))
