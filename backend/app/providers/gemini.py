"""Adapter Google Gemini (REST, streaming SSE).

API key chỉ gửi qua header x-goog-api-key, KHÔNG đưa vào URL để không lọt vào log/thông báo lỗi.
"""
from __future__ import annotations

import json
from typing import AsyncIterator, Optional

import httpx

from .base import Provider, ProviderError, QuotaExceeded, SafetyBlocked, iter_sse_data

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
_SAFETY_FINISH = {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "IMAGE_SAFETY"}


class GeminiProvider(Provider):
    name = "gemini"

    def __init__(self, api_key: str, client: Optional[httpx.AsyncClient] = None, timeout: float = 30.0):
        self._api_key = api_key
        self._client = client or httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def stream(self, model: str, prompt: str) -> AsyncIterator[str]:
        url = f"{_BASE_URL}/models/{model}:streamGenerateContent?alt=sse"
        headers = {"x-goog-api-key": self._api_key, "Content-Type": "application/json"}
        body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
        try:
            async with self._client.stream("POST", url, json=body, headers=headers) as resp:
                if resp.status_code == 429:
                    raise QuotaExceeded("Gemini: hết hạn mức (HTTP 429)")
                if resp.status_code >= 400:
                    raise ProviderError(f"Gemini: HTTP {resp.status_code}")
                async for data in iter_sse_data(resp):
                    try:
                        obj = json.loads(data)
                    except json.JSONDecodeError as exc:
                        raise ProviderError("Gemini: dữ liệu trả về không đúng định dạng") from exc
                    if "error" in obj:
                        code = obj["error"].get("code") if isinstance(obj["error"], dict) else None
                        if code == 429:
                            raise QuotaExceeded("Gemini: hết hạn mức")
                        raise ProviderError("Gemini: nhà cung cấp báo lỗi")
                    if obj.get("promptFeedback", {}).get("blockReason"):
                        raise SafetyBlocked("Gemini: yêu cầu bị chặn bởi bộ lọc an toàn")
                    for cand in obj.get("candidates", []):
                        for part in cand.get("content", {}).get("parts", []):
                            text = part.get("text")
                            if text:
                                yield text
                        if cand.get("finishReason") in _SAFETY_FINISH:
                            raise SafetyBlocked("Gemini: câu trả lời bị chặn bởi bộ lọc an toàn")
        except httpx.HTTPError as exc:
            raise ProviderError(f"Gemini: lỗi mạng ({type(exc).__name__})") from None
