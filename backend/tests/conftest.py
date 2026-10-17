"""Cấu hình dùng chung cho test: 3 model giả, giới hạn nhỏ để test nhanh."""
import pytest
import yaml

from app.config import CATEGORIES, load_config


@pytest.fixture
def cfg(tmp_path):
    routes = {cat: ["a", "b", "c"] for cat in CATEGORIES}
    routes["code"] = ["b", "a", "c"]  # câu hỏi code ưu tiên model b trước
    data = {
        "timeout_seconds": 0.2,   # nhỏ để test timeout nhanh
        "daily_limit": 2,
        "ip_daily_limit": 5,
        "max_prompt_chars": 100,
        "max_response_chars": 50,
        "long_prompt_chars": 1500,
        "models": {
            "a": {"provider": "gemini", "model": "model-a", "label": "A"},
            "b": {"provider": "openrouter", "model": "model-b", "label": "B"},
            "c": {"provider": "gemini", "model": "model-c", "label": "C"},
        },
        "routes": routes,
    }
    p = tmp_path / "models.yaml"
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    return load_config(p)
