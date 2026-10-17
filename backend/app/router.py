"""Router: chọn model phù hợp theo loại câu hỏi, tự chuyển model khi lỗi.

Sự kiện (dict) do Router.stream phát ra:
  {"type": "meta", "model", "label", "category"}   - model đã trả lời được đoạn đầu tiên
  {"type": "chunk", "text"}                         - một đoạn câu trả lời
  {"type": "done"}                                  - kết thúc bình thường
  {"type": "blocked", "model", "label", "message"}  - model từ chối vì bộ lọc an toàn (KHÔNG thử model khác)
  {"type": "error", "message"}                      - lỗi giữa chừng sau khi đã có chữ (không đổi model được nữa)

Nếu không model nào ra được đoạn đầu tiên: raise AllModelsFailed.
Fallback chỉ áp dụng TRƯỚC khi có đoạn chữ đầu tiên (lỗi, hết quota, quá timeout, trả lời rỗng).
Khi người dùng chọn tay một model thì không fallback.
"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator, Callable, Optional

from .classifier import classify
from .config import Config, ModelSpec
from .providers.base import Provider, ProviderError, SafetyBlocked

_BLOCKED_MESSAGE = "Model từ chối trả lời yêu cầu này vì bộ lọc an toàn."
_STREAM_ERROR_MESSAGE = "Kết nối bị gián đoạn giữa chừng. Bạn hãy thử gửi lại."


class UnknownModel(ValueError):
    """Người dùng chọn tay một model không có trong cấu hình."""


class AllModelsFailed(Exception):
    """Không model nào trả lời được."""

    def __init__(self, message: str, errors: Optional[list[str]] = None):
        super().__init__(message)
        self.errors = errors or []


async def _close(agen) -> None:
    aclose = getattr(agen, "aclose", None)
    if aclose is not None:
        try:
            await aclose()
        except Exception:  # đóng generator không được làm hỏng luồng chính
            pass


def _describe(spec: ModelSpec, reason: str) -> str:
    return f"{spec.id}: {reason[:200]}"


class Router:
    def __init__(self, config: Config, providers: dict[str, Provider],
                 classify_fn: Callable[..., str] = classify):
        self._config = config
        self._providers = providers
        self._classify = classify_fn

    def plan(self, prompt: str, forced_model: Optional[str] = None) -> tuple[str, list[ModelSpec]]:
        """Trả về (loại câu hỏi, danh sách model theo thứ tự ưu tiên, đã bỏ model thiếu nhà cung cấp)."""
        cfg = self._config
        if forced_model:
            spec = cfg.models.get(forced_model)
            if spec is None:
                raise UnknownModel(forced_model)
            return "manual", ([spec] if spec.provider in self._providers else [])
        category = self._classify(prompt, cfg.long_prompt_chars)
        candidates = [cfg.models[i] for i in cfg.routes[category]
                      if cfg.models[i].provider in self._providers]
        return category, candidates

    async def stream(self, prompt: str, forced_model: Optional[str] = None) -> AsyncIterator[dict]:
        category, candidates = self.plan(prompt, forced_model)
        if not candidates:
            raise AllModelsFailed("Chưa có nhà cung cấp AI nào được cấu hình")

        timeout = self._config.timeout_seconds
        errors: list[str] = []
        for spec in candidates:
            agen = self._providers[spec.provider].stream(spec.model, prompt)
            try:
                first = await asyncio.wait_for(agen.__anext__(), timeout)
            except StopAsyncIteration:
                errors.append(_describe(spec, "trả lời rỗng"))
                continue
            except asyncio.TimeoutError:
                errors.append(_describe(spec, f"quá {timeout}s chưa có phản hồi"))
                await _close(agen)
                continue
            except SafetyBlocked:
                await _close(agen)
                yield {"type": "blocked", "model": spec.id, "label": spec.label,
                       "message": _BLOCKED_MESSAGE}
                return
            except Exception as exc:  # ProviderError, QuotaExceeded và cả lỗi bất ngờ đều thử model kế
                errors.append(_describe(spec, f"{type(exc).__name__}: {exc}"))
                await _close(agen)
                continue

            # Model này đã ra chữ đầu tiên: chốt dùng model này
            try:
                yield {"type": "meta", "model": spec.id, "label": spec.label, "category": category}
                yield {"type": "chunk", "text": first}
                try:
                    async for text in agen:
                        yield {"type": "chunk", "text": text}
                except SafetyBlocked:
                    yield {"type": "blocked", "model": spec.id, "label": spec.label,
                           "message": _BLOCKED_MESSAGE}
                    return
                except Exception:
                    yield {"type": "error", "message": _STREAM_ERROR_MESSAGE}
                    return
                yield {"type": "done"}
                return
            finally:
                await _close(agen)

        raise AllModelsFailed("Tất cả model đều không trả lời được", errors)
