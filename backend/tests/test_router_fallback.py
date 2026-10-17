"""Bước 5: tự chuyển model khi lỗi / hết quota / quá thời gian; không vượt bộ lọc an toàn."""
import time

import pytest

from app.providers.base import ProviderError, QuotaExceeded, SafetyBlocked
from app.providers.fake import FakeProvider
from app.router import AllModelsFailed, Router


async def run(router, prompt="Chào bạn", forced=None):
    return [e async for e in router.stream(prompt, forced_model=forced)]


def types(events):
    return [e["type"] for e in events]


def model_of(events):
    return next(e["model"] for e in events if e["type"] == "meta")


async def test_falls_back_on_provider_error_before_first_chunk(cfg):
    gemini = FakeProvider(error=ProviderError("5xx"))      # model a, c (gemini) lỗi
    openrouter = FakeProvider(chunks=("ok",))              # model b
    events = await run(Router(cfg, {"gemini": gemini, "openrouter": openrouter}))
    assert model_of(events) == "b"
    assert types(events) == ["meta", "chunk", "done"]      # người dùng không thấy lỗi của model a


async def test_falls_back_on_quota_exceeded(cfg):
    gemini = FakeProvider(error=QuotaExceeded("429"))
    openrouter = FakeProvider(chunks=("ok",))
    events = await run(Router(cfg, {"gemini": gemini, "openrouter": openrouter}))
    assert model_of(events) == "b"


async def test_falls_back_on_timeout_quickly(cfg):
    gemini = FakeProvider(chunks=("chậm",), delay=1.0)     # timeout cấu hình là 0.2s
    openrouter = FakeProvider(chunks=("nhanh",))
    start = time.monotonic()
    events = await run(Router(cfg, {"gemini": gemini, "openrouter": openrouter}))
    assert model_of(events) == "b"
    assert time.monotonic() - start < 0.9


async def test_empty_answer_counts_as_failure(cfg):
    gemini = FakeProvider(chunks=())
    openrouter = FakeProvider(chunks=("ok",))
    events = await run(Router(cfg, {"gemini": gemini, "openrouter": openrouter}))
    assert model_of(events) == "b"


async def test_unexpected_exception_also_falls_back(cfg):
    gemini = FakeProvider(error=RuntimeError("lỗi bất ngờ"))
    openrouter = FakeProvider(chunks=("ok",))
    events = await run(Router(cfg, {"gemini": gemini, "openrouter": openrouter}))
    assert model_of(events) == "b"


async def test_all_models_fail_raises_with_one_error_per_model(cfg):
    gemini = FakeProvider(error=ProviderError("x"))
    openrouter = FakeProvider(error=QuotaExceeded("y"))
    with pytest.raises(AllModelsFailed) as info:
        await run(Router(cfg, {"gemini": gemini, "openrouter": openrouter}))
    assert len(info.value.errors) == 3                     # a, b, c


async def test_safety_block_does_not_fall_back(cfg):
    gemini = FakeProvider(error=SafetyBlocked("blocked"))
    openrouter = FakeProvider(chunks=("không được gọi",))
    events = await run(Router(cfg, {"gemini": gemini, "openrouter": openrouter}))
    assert types(events) == ["blocked"]
    assert events[0]["model"] == "a"
    assert openrouter.calls == []                           # không cố vượt bộ lọc bằng model khác


async def test_mid_stream_failure_emits_error_and_does_not_switch_model(cfg):
    gemini = FakeProvider(chunks=("a", "b", "c"), error=ProviderError("đứt"), error_after=1)
    openrouter = FakeProvider(chunks=("không được gọi",))
    events = await run(Router(cfg, {"gemini": gemini, "openrouter": openrouter}))
    assert types(events) == ["meta", "chunk", "error"]
    assert openrouter.calls == []


async def test_forced_model_failure_does_not_fall_back(cfg):
    gemini = FakeProvider(chunks=("ok",))
    openrouter = FakeProvider(error=ProviderError("x"))
    with pytest.raises(AllModelsFailed):
        await run(Router(cfg, {"gemini": gemini, "openrouter": openrouter}), forced="b")
    assert gemini.calls == []                               # người dùng chọn tay thì tôn trọng lựa chọn
