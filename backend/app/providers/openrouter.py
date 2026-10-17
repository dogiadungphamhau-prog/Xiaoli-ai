"""Adapter OpenRouter (API tương thích OpenAI, streaming SSE)."""
from __future__ import annotations

import json
from typing import AsyncIterator, Optional

import httpx

from .base import Provider, ProviderError, QuotaExceeded, SafetyBlocked, iter_sse_data

_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterProvider(Provider):
    name = "openrouter"

    def __init__(self, api_key: str, client: Optional[httpx.AsyncClient] = None,
                 timeout: float = 30.0, app_title: str = "Xiaoli AI"):
        self._api_key = api_key
        self._app_title = app_title
        self._client = client or httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def stream(self, model: str, prompt: str) -> AsyncIterator[str]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "X-Title": self._app_title,
        }
        body = {"model": model, "stream": True, "messages": [{"role": "user", "content": prompt}]}
        try:
            async with self._client.stream("POST", _URL, json=body, headers=headers) as resp:
                if resp.status_code == 429:
                    raise QuotaExceeded("OpenRouter: hết hạn mức (HTTP 429)")
                if resp.status_code >= 400:
                    raise ProviderError(f"OpenRouter: HTTP {resp.status_code}")
                async for data in iter_sse_data(resp):
                    if data == "[DONE]":
                        return
                    try:
                        obj = json.loads(data)
                    except json.JSONDecodeError as exc:
                        raise ProviderError("OpenRouter: dữ liệu trả về không đúng định dạng") from exc
                    if "error" in obj:
                        code = obj["error"].get("code") if isinstance(obj["error"], dict) else None
                        if code == 429:
                            raise QuotaExceeded("OpenRouter: hết hạn mức")
                        raise ProviderError("OpenRouter: nhà cung cấp báo lỗi")
                    for choice in obj.get("choices", []):
                        text = (choice.get("delta") or {}).get("content")
                        if text:
                            yield text
                        if choice.get("finish_reason") == "content_filter":
                            raise SafetyBlocked("OpenRouter: câu trả lời bị chặn bởi bộ lọc an toàn")
        except httpx.HTTPError as exc:
            raise ProviderError(f"OpenRouter: lỗi mạng ({type(exc).__name__})") from None
