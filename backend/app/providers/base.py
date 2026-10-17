"""Giao diện chung cho mọi nhà cung cấp AI."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator


class ProviderError(Exception):
    """Lỗi kỹ thuật từ nhà cung cấp (mạng, 5xx, định dạng sai...). Router sẽ thử model khác."""


class QuotaExceeded(ProviderError):
    """Hết hạn mức (HTTP 429). Router sẽ thử model khác."""


class SafetyBlocked(ProviderError):
    """Model từ chối vì bộ lọc an toàn. Router KHÔNG thử model khác (không cố vượt bộ lọc)."""


class Provider(ABC):
    """Mỗi nhà cung cấp phục vụ nhiều model; tên model truyền vào mỗi lần gọi."""

    name: str = "provider"

    @abstractmethod
    def stream(self, model: str, prompt: str) -> AsyncIterator[str]:
        """Trả về từng đoạn chữ của câu trả lời. Lỗi thì raise ProviderError (hoặc lớp con)."""


async def iter_sse_data(response) -> AsyncIterator[str]:
    """Đọc luồng Server-Sent Events của httpx, trả về phần sau 'data:' của từng dòng.
    Bỏ qua dòng trống và dòng chú thích (bắt đầu bằng ':')."""
    async for line in response.aiter_lines():
        if line.startswith("data:"):
            yield line[5:].strip()
