"""Giới hạn số lượt dùng mỗi ngày theo một khóa (ID thiết bị hoặc địa chỉ IP).

- Ngày tính theo giờ Việt Nam (UTC+7), reset lúc 0h.
- Lưu trong bộ nhớ của tiến trình: khởi động lại server thì đếm lại từ đầu,
  và chỉ đúng khi chạy MỘT bản server. Khi cần nhiều bản, chuyển sang Redis/database.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Optional

VN_TZ = timezone(timedelta(hours=7))


@dataclass(frozen=True)
class RateResult:
    allowed: bool
    remaining: int
    reset_at: datetime  # thời điểm reset kế tiếp (0h giờ VN), có múi giờ


class RateLimiter:
    def __init__(self, limit: int, clock: Optional[Callable[[], datetime]] = None,
                 max_keys: int = 100_000):
        if limit <= 0:
            raise ValueError("limit phải lớn hơn 0")
        self._limit = limit
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._max_keys = max_keys
        self._day: Optional[date] = None
        self._counts: dict[str, int] = {}

    def consume(self, key: str) -> RateResult:
        """Tính một lượt cho `key`. Nếu đã hết lượt thì từ chối và không tăng bộ đếm."""
        now_vn = self._clock().astimezone(VN_TZ)
        today = now_vn.date()
        if today != self._day:       # sang ngày mới: xóa toàn bộ bộ đếm cũ
            self._day = today
            self._counts = {}
        next_midnight = datetime(today.year, today.month, today.day, tzinfo=VN_TZ) + timedelta(days=1)

        used = self._counts.get(key)
        if used is None:
            if len(self._counts) >= self._max_keys:
                return RateResult(False, 0, next_midnight)
            used = 0
        if used >= self._limit:
            return RateResult(False, 0, next_midnight)
        self._counts[key] = used + 1
        return RateResult(True, self._limit - used - 1, next_midnight)
