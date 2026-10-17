"""Bước 8: API FastAPI (/health, /models, /chat streaming), giới hạn lượt, CORS."""
import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import create_app, create_app_from_env
from app.providers.base import ProviderError, SafetyBlocked
from app.providers.fake import FakeProvider

NOW = datetime(2026, 10, 17, 3, 0, tzinfo=timezone.utc)


def build(cfg, providers=None, **kw):
    if providers is None:
        providers = {"gemini": FakeProvider(chunks=("Xin ", "chào")),
                     "openrouter": FakeProvider(chunks=("or",))}
    app = create_app(cfg, providers, clock=lambda: NOW, **kw)
    return TestClient(app), providers


def chat(client, prompt="Chào bạn", device="device-0001", model=None, headers=None):
    h = {"X-Device-Id": device} if device else {}
    h.update(headers or {})
    body = {"prompt": prompt}
    if model:
        body["model"] = model
    return client.post("/chat", json=body, headers=h)


def events(resp):
    return [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]


def test_health(cfg):
    client, _ = build(cfg)
    assert client.get("/health").json() == {"status": "ok"}


def test_models_lists_only_available_models(cfg):
    client, _ = build(cfg, {"gemini": FakeProvider()})
    ids = [m["id"] for m in client.get("/models").json()["models"]]
    assert ids == ["a", "c"]        # b thuộc openrouter, chưa cấu hình


def test_chat_streams_meta_chunks_done_and_quota_header(cfg):
    client, _ = build(cfg)
    resp = chat(client)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    evs = events(resp)
    assert evs[0] == {"type": "meta", "model": "a", "label": "A", "category": "quick"}
    assert "".join(e["text"] for e in evs if e["type"] == "chunk") == "Xin chào"
    assert evs[-1] == {"type": "done"}
    assert resp.headers["x-ratelimit-remaining"] == "1"      # daily_limit = 2, đã dùng 1


@pytest.mark.parametrize("device", [None, "short", "co dau cach & ky tu la!!", "x" * 65])
def test_chat_requires_valid_device_id(cfg, device):
    client, _ = build(cfg)
    assert chat(client, device=device).status_code == 400


def test_chat_rejects_empty_prompt(cfg):
    client, _ = build(cfg)
    assert chat(client, prompt="   ").status_code == 400


def test_chat_rejects_too_long_prompt(cfg):
    client, _ = build(cfg)
    assert chat(client, prompt="a" * 101).status_code == 413     # max_prompt_chars = 100


def test_chat_rejects_unknown_model(cfg):
    client, _ = build(cfg)
    assert chat(client, model="khong_co").status_code == 400


def test_invalid_requests_do_not_consume_quota(cfg):
    client, _ = build(cfg)
    chat(client, prompt="   ")
    chat(client, model="khong_co")
    assert chat(client).headers["x-ratelimit-remaining"] == "1"


def test_chat_manual_model_is_used(cfg):
    client, providers = build(cfg)
    evs = events(chat(client, model="b"))
    assert evs[0]["model"] == "b"
    assert providers["openrouter"].calls == [("model-b", "Chào bạn")]


def test_device_rate_limit_returns_429_with_reset_time(cfg):
    client, _ = build(cfg)
    assert chat(client).status_code == 200
    assert chat(client).status_code == 200
    resp = chat(client)
    assert resp.status_code == 429
    body = resp.json()
    assert body["remaining"] == 0
    assert body["reset_at"].startswith("2026-10-17T17:00:00")   # 0h giờ VN ngày 18 = 17:00 UTC


def test_ip_rate_limit_applies_across_devices(cfg):
    client, _ = build(cfg)                      # ip_daily_limit = 5
    codes = [chat(client, device=f"device-{i:04d}").status_code for i in range(6)]
    assert codes == [200] * 5 + [429]


def test_forwarded_header_ignored_unless_proxy_is_trusted(cfg):
    client, _ = build(cfg, trust_proxy=False)
    codes = [chat(client, device=f"device-{i:04d}",
                  headers={"X-Forwarded-For": f"10.0.0.{i}"}).status_code for i in range(6)]
    assert codes[-1] == 429                     # kẻ gian giả X-Forwarded-For cũng không né được giới hạn


def test_forwarded_header_used_when_proxy_is_trusted(cfg):
    client, _ = build(cfg, trust_proxy=True)
    codes = [chat(client, device=f"device-{i:04d}",
                  headers={"X-Forwarded-For": f"10.0.0.{i}, 172.16.0.1"}).status_code for i in range(6)]
    assert codes == [200] * 6                   # mỗi người dùng thật có bộ đếm IP riêng sau proxy


def test_all_models_failing_returns_503_without_leaking_details(cfg):
    boom = {"gemini": FakeProvider(error=ProviderError("chi tiết nội bộ bí mật")),
            "openrouter": FakeProvider(error=ProviderError("chi tiết nội bộ bí mật"))}
    client, _ = build(cfg, boom)
    resp = chat(client)
    assert resp.status_code == 503
    assert "bí mật" not in resp.text


def test_no_provider_configured_returns_503_and_keeps_quota(cfg):
    client, _ = build(cfg, {})
    assert chat(client).status_code == 503
    client2, _ = build(cfg, {"gemini": FakeProvider()})
    assert chat(client2).headers["x-ratelimit-remaining"] == "1"


def test_safety_block_is_reported_as_event(cfg):
    client, _ = build(cfg, {"gemini": FakeProvider(error=SafetyBlocked("x")), "openrouter": FakeProvider()})
    resp = chat(client)
    assert resp.status_code == 200
    assert [e["type"] for e in events(resp)] == ["blocked"]


def test_mid_stream_failure_is_reported_as_error_event(cfg):
    p = FakeProvider(chunks=("a", "b"), error=ProviderError("đứt"), error_after=1)
    client, _ = build(cfg, {"gemini": p, "openrouter": FakeProvider()})
    assert [e["type"] for e in events(chat(client))] == ["meta", "chunk", "error"]


def test_response_is_truncated_at_max_response_chars(cfg):
    p = FakeProvider(chunks=("x" * 30, "y" * 30))               # max_response_chars = 50
    client, _ = build(cfg, {"gemini": p, "openrouter": FakeProvider()})
    evs = events(chat(client))
    assert "".join(e["text"] for e in evs if e["type"] == "chunk") == "x" * 30 + "y" * 20
    assert evs[-1] == {"type": "done", "truncated": True}


def test_cors_allows_only_configured_origin(cfg):
    client, _ = build(cfg, allowed_origins=["https://xiaoli.example"])
    ok = client.options("/chat", headers={"Origin": "https://xiaoli.example",
                                          "Access-Control-Request-Method": "POST"})
    bad = client.options("/chat", headers={"Origin": "https://evil.example",
                                           "Access-Control-Request-Method": "POST"})
    assert ok.headers.get("access-control-allow-origin") == "https://xiaoli.example"
    assert "access-control-allow-origin" not in bad.headers


def test_no_cors_headers_when_no_origins_configured(cfg):
    client, _ = build(cfg)
    resp = client.get("/health", headers={"Origin": "https://xiaoli.example"})
    assert "access-control-allow-origin" not in resp.headers


def test_frontend_dir_is_served_at_root(cfg, tmp_path):
    (tmp_path / "index.html").write_text("<h1>Xiaoli AI</h1>", encoding="utf-8")
    client, _ = build(cfg, frontend_dir=tmp_path)
    assert "Xiaoli AI" in client.get("/").text
    assert client.get("/health").json() == {"status": "ok"}     # API không bị che


def test_env_factory_without_keys_has_no_providers(monkeypatch, tmp_path):
    for k in ("GEMINI_API_KEY", "OPENROUTER_API_KEY", "ALLOWED_ORIGINS", "TRUST_PROXY", "XIAOLI_CONFIG"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("XIAOLI_FRONTEND", str(tmp_path / "khong_co"))
    client = TestClient(create_app_from_env())
    assert client.get("/models").json()["models"] == []
    assert chat(client).status_code == 503


def test_env_factory_registers_provider_when_key_is_set(monkeypatch, tmp_path):
    for k in ("OPENROUTER_API_KEY", "ALLOWED_ORIGINS", "TRUST_PROXY", "XIAOLI_CONFIG"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-key-for-test")
    monkeypatch.setenv("XIAOLI_FRONTEND", str(tmp_path / "khong_co"))
    client = TestClient(create_app_from_env())
    providers = {m["id"] for m in client.get("/models").json()["models"]}
    assert providers == {"gemini_flash", "gemini_flash_lite"}
