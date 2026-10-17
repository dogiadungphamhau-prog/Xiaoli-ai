"""Bước 7: adapter Gemini và OpenRouter, kiểm thử bằng HTTP giả (httpx.MockTransport)."""
import json

import httpx
import pytest

from app.providers.base import ProviderError, QuotaExceeded, SafetyBlocked
from app.providers.gemini import GeminiProvider
from app.providers.openrouter import OpenRouterProvider

SECRET = "SECRET-KEY-123"


def sse(*objs, raw=()):
    lines = [f"data: {json.dumps(o)}\n\n" for o in objs] + [f"{r}\n\n" for r in raw]
    return "".join(lines).encode("utf-8")


def client_for(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def collect(agen):
    return [x async for x in agen]


def gem_event(text, finish=None):
    cand = {"content": {"parts": [{"text": text}]}}
    if finish:
        cand["finishReason"] = finish
    return {"candidates": [cand]}


def or_event(text, finish=None):
    return {"choices": [{"delta": {"content": text}, "finish_reason": finish}]}


# ===================== Gemini =====================

async def test_gemini_streams_text_and_builds_correct_request():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["headers"] = request.headers
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, content=sse(gem_event("Xin "), gem_event("chào")))

    p = GeminiProvider(SECRET, client=client_for(handler))
    assert await collect(p.stream("gemini-x", "câu hỏi")) == ["Xin ", "chào"]
    assert "models/gemini-x:streamGenerateContent" in seen["url"]
    assert "alt=sse" in seen["url"]
    assert SECRET not in seen["url"]                      # key chỉ nằm trong header, không nằm trong URL
    assert seen["headers"]["x-goog-api-key"] == SECRET
    assert seen["body"]["contents"][0]["parts"][0]["text"] == "câu hỏi"


async def test_gemini_ignores_events_without_text():
    def handler(request):
        return httpx.Response(200, content=sse({"usageMetadata": {"totalTokenCount": 3}}, gem_event("ok")))

    p = GeminiProvider(SECRET, client=client_for(handler))
    assert await collect(p.stream("m", "q")) == ["ok"]


async def test_gemini_429_is_quota_exceeded():
    p = GeminiProvider(SECRET, client=client_for(lambda r: httpx.Response(429)))
    with pytest.raises(QuotaExceeded):
        await collect(p.stream("m", "q"))


async def test_gemini_500_is_provider_error_not_quota():
    p = GeminiProvider(SECRET, client=client_for(lambda r: httpx.Response(500)))
    with pytest.raises(ProviderError) as info:
        await collect(p.stream("m", "q"))
    assert not isinstance(info.value, QuotaExceeded)


async def test_gemini_prompt_block_is_safety_blocked():
    body = sse({"promptFeedback": {"blockReason": "SAFETY"}})
    p = GeminiProvider(SECRET, client=client_for(lambda r: httpx.Response(200, content=body)))
    with pytest.raises(SafetyBlocked):
        await collect(p.stream("m", "q"))


async def test_gemini_finish_reason_safety_is_safety_blocked():
    body = sse({"candidates": [{"finishReason": "SAFETY"}]})
    p = GeminiProvider(SECRET, client=client_for(lambda r: httpx.Response(200, content=body)))
    with pytest.raises(SafetyBlocked):
        await collect(p.stream("m", "q"))


async def test_gemini_network_error_is_provider_error_without_leaking_key():
    def handler(request):
        raise httpx.ConnectError("không kết nối được", request=request)

    p = GeminiProvider(SECRET, client=client_for(handler))
    with pytest.raises(ProviderError) as info:
        await collect(p.stream("m", "q"))
    assert SECRET not in str(info.value)


async def test_gemini_invalid_json_is_provider_error():
    p = GeminiProvider(SECRET, client=client_for(lambda r: httpx.Response(200, content=b"data: {khong phai json\n\n")))
    with pytest.raises(ProviderError):
        await collect(p.stream("m", "q"))


# ===================== OpenRouter =====================

async def test_openrouter_streams_ignores_comments_and_stops_at_done():
    seen = {}

    def handler(request):
        seen["headers"] = request.headers
        seen["body"] = json.loads(request.content)
        content = b": OPENROUTER PROCESSING\n\n" + sse(or_event("Xin "), or_event(None), or_event("chào"),
                                                       raw=["data: [DONE]"])
        content += sse(or_event("KHÔNG ĐƯỢC ĐỌC"))
        return httpx.Response(200, content=content)

    p = OpenRouterProvider(SECRET, client=client_for(handler))
    assert await collect(p.stream("vendor/model:free", "câu hỏi")) == ["Xin ", "chào"]
    assert seen["headers"]["authorization"] == f"Bearer {SECRET}"
    assert seen["body"] == {"model": "vendor/model:free", "stream": True,
                            "messages": [{"role": "user", "content": "câu hỏi"}]}


async def test_openrouter_429_is_quota_exceeded():
    p = OpenRouterProvider(SECRET, client=client_for(lambda r: httpx.Response(429)))
    with pytest.raises(QuotaExceeded):
        await collect(p.stream("m", "q"))


async def test_openrouter_401_is_provider_error():
    p = OpenRouterProvider(SECRET, client=client_for(lambda r: httpx.Response(401)))
    with pytest.raises(ProviderError) as info:
        await collect(p.stream("m", "q"))
    assert not isinstance(info.value, QuotaExceeded)


async def test_openrouter_in_stream_error_object_is_provider_error():
    body = sse({"error": {"code": 502, "message": "upstream lỗi"}})
    p = OpenRouterProvider(SECRET, client=client_for(lambda r: httpx.Response(200, content=body)))
    with pytest.raises(ProviderError):
        await collect(p.stream("m", "q"))


async def test_openrouter_in_stream_429_is_quota_exceeded():
    body = sse({"error": {"code": 429, "message": "rate limit"}})
    p = OpenRouterProvider(SECRET, client=client_for(lambda r: httpx.Response(200, content=body)))
    with pytest.raises(QuotaExceeded):
        await collect(p.stream("m", "q"))


async def test_openrouter_content_filter_is_safety_blocked():
    body = sse(or_event("", finish="content_filter"))
    p = OpenRouterProvider(SECRET, client=client_for(lambda r: httpx.Response(200, content=body)))
    with pytest.raises(SafetyBlocked):
        await collect(p.stream("m", "q"))


async def test_openrouter_network_error_is_provider_error_without_leaking_key():
    def handler(request):
        raise httpx.ReadTimeout("quá thời gian", request=request)

    p = OpenRouterProvider(SECRET, client=client_for(handler))
    with pytest.raises(ProviderError) as info:
        await collect(p.stream("m", "q"))
    assert SECRET not in str(info.value)
