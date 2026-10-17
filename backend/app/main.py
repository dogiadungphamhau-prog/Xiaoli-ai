"""API của Xiaoli AI.

  GET  /health   - kiểm tra server sống
  GET  /models   - danh sách model có thể chọn tay (chỉ model có nhà cung cấp đã cấu hình)
  POST /chat     - gửi câu hỏi, nhận câu trả lời dạng Server-Sent Events
                   (header bắt buộc: X-Device-Id)

Chạy: uvicorn app.main:create_app_from_env --factory
Biến môi trường: GEMINI_API_KEY, OPENROUTER_API_KEY, ALLOWED_ORIGINS, TRUST_PROXY,
                 XIAOLI_CONFIG, XIAOLI_FRONTEND.
Quyền riêng tư: server KHÔNG ghi nội dung câu hỏi/câu trả lời vào log.
"""
from __future__ import annotations

import json
import logging
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Optional

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import Config, load_config
from .providers.base import Provider
from .providers.gemini import GeminiProvider
from .providers.openrouter import OpenRouterProvider
from .ratelimit import RateLimiter
from .router import AllModelsFailed, Router, UnknownModel

logger = logging.getLogger("xiaoli")

_DEVICE_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


class ChatRequest(BaseModel):
    prompt: str
    model: Optional[str] = None   # None hoặc "auto" = để router tự chọn


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def _client_ip(request: Request, trust_proxy: bool) -> str:
    if trust_proxy:
        forwarded = request.headers.get("x-forwarded-for", "")
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"


def create_app(
    config: Config,
    providers: dict[str, Provider],
    *,
    allowed_origins: Iterable[str] = (),
    trust_proxy: bool = False,
    frontend_dir: Optional[Path] = None,
    clock: Optional[Callable[[], datetime]] = None,
) -> FastAPI:
    router = Router(config, providers)
    device_limiter = RateLimiter(config.daily_limit, clock=clock)
    ip_limiter = RateLimiter(config.ip_daily_limit, clock=clock)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        for provider in providers.values():
            aclose = getattr(provider, "aclose", None)
            if aclose is not None:
                await aclose()

    app = FastAPI(title="Xiaoli AI", lifespan=lifespan)

    origins = list(allowed_origins)
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type", "X-Device-Id"],
            expose_headers=["X-RateLimit-Remaining", "X-RateLimit-Reset"],
        )

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/models")
    async def models():
        return {"models": [{"id": s.id, "label": s.label}
                           for s in config.models.values() if s.provider in providers]}

    @app.post("/chat")
    async def chat(body: ChatRequest, request: Request, x_device_id: Optional[str] = Header(default=None)):
        # 1) Kiểm tra đầu vào (yêu cầu sai không tốn lượt)
        if not x_device_id or not _DEVICE_ID.match(x_device_id):
            raise HTTPException(400, "Thiếu hoặc sai mã thiết bị (X-Device-Id)")
        prompt = body.prompt.strip()
        if not prompt:
            raise HTTPException(400, "Câu hỏi không được để trống")
        if len(prompt) > config.max_prompt_chars:
            raise HTTPException(413, f"Câu hỏi quá dài (tối đa {config.max_prompt_chars} ký tự)")
        forced = None if body.model in (None, "", "auto") else body.model
        try:
            _, candidates = router.plan(prompt, forced)
        except UnknownModel:
            raise HTTPException(400, "Model được chọn không tồn tại")
        if not candidates:
            return JSONResponse({"detail": "Hiện chưa có model AI nào sẵn sàng. Vui lòng thử lại sau."},
                                status_code=503)

        # 2) Giới hạn lượt theo IP và thiết bị
        ip = _client_ip(request, trust_proxy)
        ip_result = ip_limiter.consume(f"ip:{ip}")
        device_result = device_limiter.consume(f"dev:{x_device_id}") if ip_result.allowed else None
        if not ip_result.allowed or not device_result.allowed:
            reset_at = (device_result or ip_result).reset_at
            return JSONResponse(
                {"detail": "Bạn đã dùng hết lượt hôm nay. Lượt sẽ được làm mới lúc 0h (giờ Việt Nam).",
                 "remaining": 0, "reset_at": reset_at.astimezone(timezone.utc).isoformat()},
                status_code=429,
            )
        rate_headers = {
            "X-RateLimit-Remaining": str(device_result.remaining),
            "X-RateLimit-Reset": device_result.reset_at.astimezone(timezone.utc).isoformat(),
        }

        # 3) Lấy sự kiện đầu tiên trước để còn trả đúng mã lỗi HTTP nếu mọi model đều hỏng
        agen = router.stream(prompt, forced)
        try:
            first = await agen.__anext__()
        except AllModelsFailed as exc:
            logger.warning("Tất cả model đều lỗi: %s", exc.errors)   # chỉ ghi tên model + loại lỗi, không ghi nội dung
            return JSONResponse({"detail": "Các model AI đang bận hoặc gặp sự cố. Vui lòng thử lại sau ít phút."},
                                status_code=503)

        async def body_stream():
            sent = 0
            event = first
            try:
                while True:
                    if event["type"] == "chunk":
                        text = event["text"]
                        room = config.max_response_chars - sent
                        truncated = len(text) > room
                        text = text[:room]
                        sent += len(text)
                        if text:
                            yield _sse({"type": "chunk", "text": text})
                        if truncated:
                            yield _sse({"type": "done", "truncated": True})
                            return
                    else:
                        yield _sse(event)
                    event = await agen.__anext__()
            except StopAsyncIteration:
                pass
            finally:
                await agen.aclose()

        return StreamingResponse(body_stream(), media_type="text/event-stream", headers=rate_headers)

    # Phục vụ giao diện PWA ở gốc (đặt SAU các route API để không che API)
    if frontend_dir is not None:
        app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

    return app


def create_app_from_env() -> FastAPI:
    """Dựng app từ biến môi trường (dùng với: uvicorn app.main:create_app_from_env --factory)."""
    base = Path(__file__).resolve().parents[2]
    config = load_config(os.environ.get("XIAOLI_CONFIG", base / "config" / "models.yaml"))

    providers: dict[str, Provider] = {}
    if os.environ.get("GEMINI_API_KEY"):
        providers["gemini"] = GeminiProvider(os.environ["GEMINI_API_KEY"])
    if os.environ.get("OPENROUTER_API_KEY"):
        providers["openrouter"] = OpenRouterProvider(os.environ["OPENROUTER_API_KEY"])
    if not providers:
        logger.warning("Chưa đặt GEMINI_API_KEY hoặc OPENROUTER_API_KEY: /chat sẽ trả 503")

    origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
    trust_proxy = os.environ.get("TRUST_PROXY", "").lower() in ("1", "true", "yes")
    frontend = Path(os.environ.get("XIAOLI_FRONTEND", base / "frontend"))
    return create_app(
        config, providers,
        allowed_origins=origins,
        trust_proxy=trust_proxy,
        frontend_dir=frontend if (frontend / "index.html").is_file() else None,
    )
