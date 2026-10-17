"""Đọc và kiểm tra cấu hình models.yaml."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

# Các loại câu hỏi mà classifier trả về và router phải có tuyến cho từng loại
CATEGORIES = ("code", "math", "translate", "long", "quick", "general")
PROVIDERS = ("gemini", "openrouter")
_POSITIVE_KEYS = (
    "timeout_seconds", "daily_limit", "ip_daily_limit",
    "max_prompt_chars", "max_response_chars", "long_prompt_chars",
)


class ConfigError(Exception):
    """Cấu hình sai hoặc thiếu."""


@dataclass(frozen=True)
class ModelSpec:
    id: str
    provider: str
    model: str
    label: str


@dataclass(frozen=True)
class Config:
    timeout_seconds: float
    daily_limit: int
    ip_daily_limit: int
    max_prompt_chars: int
    max_response_chars: int
    long_prompt_chars: int
    models: dict[str, ModelSpec]
    routes: dict[str, list[str]]


def load_config(path) -> Config:
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"Không tìm thấy file cấu hình: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"File cấu hình không đúng định dạng YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError("File cấu hình phải là một bảng YAML (key: value)")

    for key in _POSITIVE_KEYS:
        value = data.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise ConfigError(f"'{key}' phải là số lớn hơn 0")

    raw_models = data.get("models")
    if not isinstance(raw_models, dict) or not raw_models:
        raise ConfigError("Thiếu mục 'models'")
    models: dict[str, ModelSpec] = {}
    for mid, spec in raw_models.items():
        if not isinstance(spec, dict):
            raise ConfigError(f"Model '{mid}' cấu hình sai")
        provider = spec.get("provider")
        if provider not in PROVIDERS:
            raise ConfigError(f"Model '{mid}': nhà cung cấp '{provider}' chưa được hỗ trợ")
        name = spec.get("model")
        if not isinstance(name, str) or not name:
            raise ConfigError(f"Model '{mid}': thiếu tên model")
        models[mid] = ModelSpec(mid, provider, name, spec.get("label") or mid)

    raw_routes = data.get("routes")
    if not isinstance(raw_routes, dict):
        raise ConfigError("Thiếu mục 'routes'")
    routes: dict[str, list[str]] = {}
    for cat in CATEGORIES:
        ids = raw_routes.get(cat)
        if not isinstance(ids, list) or not ids:
            raise ConfigError(f"Thiếu tuyến model cho loại câu hỏi '{cat}'")
        for mid in ids:
            if mid not in models:
                raise ConfigError(f"Tuyến '{cat}' dùng model không tồn tại: {mid}")
        routes[cat] = list(ids)

    return Config(
        timeout_seconds=float(data["timeout_seconds"]),
        daily_limit=int(data["daily_limit"]),
        ip_daily_limit=int(data["ip_daily_limit"]),
        max_prompt_chars=int(data["max_prompt_chars"]),
        max_response_chars=int(data["max_response_chars"]),
        long_prompt_chars=int(data["long_prompt_chars"]),
        models=models,
        routes=routes,
    )
