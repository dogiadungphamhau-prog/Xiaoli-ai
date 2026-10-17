"""Bước 2: phân loại câu hỏi bằng luật đơn giản (không gọi AI)."""
import pytest

from app.classifier import classify

LONG_PROSE = "Thị trường lao động tại khu công nghiệp đang thay đổi nhanh chóng. " * 40


@pytest.mark.parametrize("text, expected", [
    # --- code ---
    ("Viết hàm python đảo ngược chuỗi", "code"),
    ("```js\nconsole.log(1)\n```", "code"),
    ("Sửa giúp tôi lỗi trong đoạn code SQL này, nó báo lỗi cú pháp ở dòng 3", "code"),
    ("Traceback (most recent call last): File main.py line 3, hãy giải thích lỗi này", "code"),
    # --- translate ---
    ("Dịch câu này sang tiếng Anh: xin chào các bạn", "translate"),
    ("Please translate this paragraph into Vietnamese for me, thank you", "translate"),
    # --- math ---
    ("Giải phương trình x^2 - 5x + 6 = 0", "math"),
    ("12 * 7 + 3 bằng bao nhiêu vậy bạn ơi, tính giúp mình", "math"),
    ("Tính đạo hàm của hàm số y = sin(x) tại điểm bất kỳ giúp mình", "math"),
    # --- quick ---
    ("Chào bạn", "quick"),
    ("Hôm nay là thứ mấy?", "quick"),
    ("", "quick"),
    # --- general ---
    ("Hãy cho tôi lời khuyên để quản lý thời gian hiệu quả hơn trong công việc hằng ngày", "general"),
    # Tránh nhận nhầm: "decode" không phải "code", "dịch vụ" không phải "dịch"
    ("Tôi muốn decode giấc mơ của tôi nghĩa là gì và ý nghĩa của nó với cuộc sống", "general"),
    ("Tư vấn dịch vụ giặt ủi tốt nhất ở Hà Nội cho gia đình nhỏ giúp tôi", "general"),
    # Ngày tháng có dấu gạch không bị coi là phép tính
    ("Sự kiện diễn ra ngày 2026-10-17 tại Bắc Ninh, bạn hãy gợi ý chương trình phù hợp", "general"),
])
def test_classify_categories(text, expected):
    assert classify(text) == expected


def test_long_prose_is_long():
    assert classify(LONG_PROSE) == "long"


def test_long_prose_with_single_code_word_stays_long():
    assert classify(LONG_PROSE + " code ") == "long"


def test_long_text_with_code_fence_is_code():
    assert classify(LONG_PROSE + "\n```python\nprint(1)\n```") == "code"


def test_translate_beats_long():
    assert classify("Dịch đoạn văn sau sang tiếng Anh: " + LONG_PROSE) == "translate"


def test_custom_long_threshold():
    text = "Hãy mô tả chi tiết cuộc sống ở một thành phố biển vào mùa hè nhé bạn " * 3
    assert classify(text, long_threshold=100) == "long"
    assert classify(text, long_threshold=10_000) == "general"
