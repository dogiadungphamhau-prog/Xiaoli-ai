"""Bước 3: giao diện chung của nhà cung cấp + nhà cung cấp giả."""
import pytest

from app.providers.base import Provider, ProviderError, QuotaExceeded, SafetyBlocked
from app.providers.fake import FakeProvider


async def collect(agen):
    return [x async for x in agen]


def test_error_hierarchy():
    assert issubclass(QuotaExceeded, ProviderError)
    assert issubclass(SafetyBlocked, ProviderError)


def test_base_cannot_be_instantiated():
    with pytest.raises(TypeError):
        Provider()


def test_fake_is_a_provider():
    assert isinstance(FakeProvider(), Provider)


async def test_fake_streams_chunks_in_order():
    p = FakeProvider(chunks=("Xin ", "chào", "!"))
    assert await collect(p.stream("m", "hi")) == ["Xin ", "chào", "!"]


async def test_fake_records_calls():
    p = FakeProvider()
    await collect(p.stream("model-x", "câu hỏi"))
    assert p.calls == [("model-x", "câu hỏi")]


async def test_fake_raises_before_first_chunk():
    p = FakeProvider(error=QuotaExceeded("hết quota"))
    got = []
    with pytest.raises(QuotaExceeded):
        async for c in p.stream("m", "hi"):
            got.append(c)
    assert got == []


async def test_fake_raises_after_n_chunks():
    p = FakeProvider(chunks=("a", "b", "c"), error=ProviderError("đứt kết nối"), error_after=2)
    got = []
    with pytest.raises(ProviderError):
        async for c in p.stream("m", "hi"):
            got.append(c)
    assert got == ["a", "b"]
