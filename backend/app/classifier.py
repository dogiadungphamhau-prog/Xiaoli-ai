"""Phân loại câu hỏi bằng luật đơn giản.

Cố ý KHÔNG dùng AI để phân loại: nhanh, miễn phí, không tốn quota.
Kết quả là một trong CATEGORIES (xem config.py).
Thứ tự ưu tiên: code > translate > math > long > quick > general.
"""
from __future__ import annotations

import re

_FLAGS = re.IGNORECASE

# Tín hiệu code (dùng \b để "decode" không bị nhận nhầm thành "code")
_CODE_WORDS = re.compile(
    r"\b(python|javascript|typescript|java|html|css|sql|json|regex|bash|api|bug|debug|"
    r"code|function|script|traceback|exception|compile|lập trình|mã nguồn|"
    r"viết hàm|viết chương trình)\b|c\+\+|c#",
    _FLAGS,
)
_CODE_FENCE = "```"

# "dịch" đứng một mình hay gặp trong "dịch vụ" nên chỉ nhận khi đi kèm từ chỉ hành động dịch
_TRANSLATE = re.compile(
    r"\bdịch\s+(câu|đoạn|bài|văn|sang|ra|giúp|hộ|cho|này|từ|qua|nghĩa|tài liệu|email|thư)\b"
    r"|\btranslate\b|\bbản dịch\b|\bdịch thuật\b",
    _FLAGS,
)

_MATH_WORDS = re.compile(
    r"\b(giải (bất )?phương trình|giải hệ|đạo hàm|tích phân|xác suất|ma trận|lượng giác|"
    r"solve|equation|derivative|integral|tính toán)\b",
    _FLAGS,
)
# Phép tính: 12*7, 3 + 4, x^2 ... ; dấu '-' chỉ tính khi có khoảng trắng 2 bên (tránh ngày tháng)
_MATH_EXPR = re.compile(r"\d\s*[+*/^×÷=]\s*[\d(a-z]|\d\s+-\s+[\d(a-z]", _FLAGS)

_QUICK_MAX_CHARS = 40
# Với văn bản dài không có khối code, cần nhiều tín hiệu code mới coi là câu hỏi code
_LONG_CODE_HITS = 3


def classify(text: str, long_threshold: int = 1500) -> str:
    text = (text or "").strip()
    is_long = len(text) > long_threshold

    code_hits = len(_CODE_WORDS.findall(text))
    if _CODE_FENCE in text or (code_hits >= _LONG_CODE_HITS if is_long else code_hits >= 1):
        return "code"
    if _TRANSLATE.search(text):
        return "translate"
    if _MATH_WORDS.search(text) or _MATH_EXPR.search(text):
        return "math"
    if is_long:
        return "long"
    if len(text) <= _QUICK_MAX_CHARS:
        return "quick"
    return "general"
