"""Bước 6: giới hạn lượt theo ngày (reset 0h giờ Việt Nam, UTC+7)."""
from datetime import datetime, timezone

import pytest

from app.ratelimit import RateLimiter

UTC = timezone.utc


def make(limit=2, start=datetime(2026, 10, 17, 3, 0, tzinfo=UTC), **kw):
    state = {"now": start}
    return RateLimiter(limit, clock=lambda: state["now"], **kw), state


def test_allows_up_to_limit_then_denies():
    rl, _ = make(limit=2)
    r1, r2, r3 = rl.consume("dev1"), rl.consume("dev1"), rl.consume("dev1")
    assert (r1.allowed, r1.remaining) == (True, 1)
    assert (r2.allowed, r2.remaining) == (True, 0)
    assert (r3.allowed, r3.remaining) == (False, 0)


def test_denied_requests_stay_denied():
    rl, _ = make(limit=1)
    rl.consume("dev1")
    assert not rl.consume("dev1").allowed
    assert not rl.consume("dev1").allowed


def test_keys_are_independent():
    rl, _ = make(limit=1)
    assert rl.consume("dev1").allowed
    assert rl.consume("dev2").allowed
    assert not rl.consume("dev1").allowed


def test_resets_at_vietnam_midnight_not_utc_midnight():
    # 16:59 UTC = 23:59 giờ VN ngày 17 -> dùng hết lượt
    rl, state = make(limit=1, start=datetime(2026, 10, 17, 16, 59, tzinfo=UTC))
    assert rl.consume("dev1").allowed
    assert not rl.consume("dev1").allowed
    # 17:01 UTC = 00:01 giờ VN ngày 18 -> được dùng lại (dù UTC vẫn là ngày 17)
    state["now"] = datetime(2026, 10, 17, 17, 1, tzinfo=UTC)
    assert rl.consume("dev1").allowed


def test_same_vietnam_day_does_not_reset():
    rl, state = make(limit=1, start=datetime(2026, 10, 17, 1, 0, tzinfo=UTC))   # 08:00 VN
    assert rl.consume("dev1").allowed
    state["now"] = datetime(2026, 10, 17, 16, 0, tzinfo=UTC)                    # 23:00 VN cùng ngày
    assert not rl.consume("dev1").allowed


def test_reset_at_is_next_vietnam_midnight():
    rl, _ = make(limit=1, start=datetime(2026, 10, 17, 10, 0, tzinfo=UTC))      # 17:00 VN
    result = rl.consume("dev1")
    assert result.reset_at == datetime(2026, 10, 17, 17, 0, tzinfo=UTC)         # 00:00 VN ngày 18


def test_max_keys_guard_denies_new_keys_but_keeps_existing():
    rl, _ = make(limit=5, max_keys=2)
    assert rl.consume("a").allowed
    assert rl.consume("b").allowed
    assert not rl.consume("c").allowed       # chống phình bộ nhớ khi bị gửi ID ngẫu nhiên
    assert rl.consume("a").allowed           # khóa đã có vẫn dùng bình thường


@pytest.mark.parametrize("bad", [0, -1])
def test_invalid_limit_raises(bad):
    with pytest.raises(ValueError):
        RateLimiter(bad)
