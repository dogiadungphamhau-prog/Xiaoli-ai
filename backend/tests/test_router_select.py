"""Bước 4: router chọn model theo loại câu hỏi (chưa xét fallback)."""
import pytest

from app.providers.fake import FakeProvider
from app.router import AllModelsFailed, Router, UnknownModel


def make_router(cfg, providers=None):
    if providers is None:
        providers = {"gemini": FakeProvider(chunks=("g",)), "openrouter": FakeProvider(chunks=("o",))}
    return Router(cfg, providers)


def ids(specs):
    return [s.id for s in specs]


def test_plan_follows_route_order_for_category(cfg):
    category, candidates = make_router(cfg).plan("Viết hàm python đảo ngược chuỗi")
    assert category == "code"
    assert ids(candidates) == ["b", "a", "c"]


def test_plan_uses_default_order_for_other_categories(cfg):
    category, candidates = make_router(cfg).plan("Chào bạn")
    assert category == "quick"
    assert ids(candidates) == ["a", "b", "c"]


def test_plan_skips_models_whose_provider_is_not_configured(cfg):
    router = make_router(cfg, {"gemini": FakeProvider()})
    _, candidates = router.plan("Viết hàm python đảo ngược chuỗi")
    assert ids(candidates) == ["a", "c"]  # b thuộc openrouter, chưa có key


def test_plan_forced_model_returns_only_that_model(cfg):
    category, candidates = make_router(cfg).plan("Chào bạn", forced_model="c")
    assert category == "manual"
    assert ids(candidates) == ["c"]


def test_plan_forced_unknown_model_raises(cfg):
    with pytest.raises(UnknownModel):
        make_router(cfg).plan("Chào bạn", forced_model="khong_co")


def test_plan_forced_model_with_missing_provider_gives_no_candidates(cfg):
    router = make_router(cfg, {"gemini": FakeProvider()})
    _, candidates = router.plan("Chào bạn", forced_model="b")
    assert candidates == []


async def test_stream_emits_meta_chunks_done_and_calls_real_model_name(cfg):
    gemini = FakeProvider(chunks=("Xin ", "chào"))
    router = make_router(cfg, {"gemini": gemini, "openrouter": FakeProvider()})
    events = [e async for e in router.stream("Chào bạn")]
    assert events[0] == {"type": "meta", "model": "a", "label": "A", "category": "quick"}
    assert [e["text"] for e in events if e["type"] == "chunk"] == ["Xin ", "chào"]
    assert events[-1] == {"type": "done"}
    assert gemini.calls == [("model-a", "Chào bạn")]


async def test_stream_without_any_provider_raises_all_failed(cfg):
    router = make_router(cfg, {})
    with pytest.raises(AllModelsFailed):
        async for _ in router.stream("Chào bạn"):
            pass
