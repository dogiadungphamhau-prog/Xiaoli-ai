"""Nhà cung cấp giả dùng cho test: không gọi mạng, không tốn quota."""
from __future__ import annotations

import asyncio
from typing import AsyncIterator, Optional

from .base import Provider


class FakeProvider(Provider):
    def __init__(
        self,
        chunks: tuple[str, ...] = ("ok",),
        error: Optional[Exception] = None,
        error_after: Optional[int] = None,
        delay: float = 0.0,
        name: str = "fake",
    ):
        self.chunks = chunks
        self.error = error
        self.error_after = error_after  # None: lỗi ngay đầu; N: lỗi sau N đoạn
        self.delay = delay              # chờ bao lâu trước đoạn đầu tiên
        self.name = name
        self.calls: list[tuple[str, str]] = []

    async def stream(self, model: str, prompt: str) -> AsyncIterator[str]:
        self.calls.append((model, prompt))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None and self.error_after is None:
            raise self.error
        for i, chunk in enumerate(self.chunks):
            if self.error is not None and self.error_after is not None and i >= self.error_after:
                raise self.error
            yield chunk
        if self.error is not None and self.error_after is not None and self.error_after >= len(self.chunks):
            raise self.error
