# Xiaoli AI (bản thử nghiệm PWA)

Hỏi một lần, router tự chọn model AI phù hợp và tự chuyển model khi lỗi.
Backend FastAPI phục vụ luôn giao diện PWA trong `frontend/`.

## Chạy trên máy
    cd backend
    pip install -r requirements.txt
    python -m pytest                       # kỳ vọng: toàn bộ test xanh
    # Windows: set GEMINI_API_KEY=...   Linux/Mac: export GEMINI_API_KEY=...
    python -m uvicorn app.main:create_app_from_env --factory --port 8000
Mở http://localhost:8000 . Kiểm tra http://localhost:8000/models có hiện model.

## Việc phải làm trước khi dùng thật
1. Tạo khóa tại Google AI Studio và OpenRouter, đặt vào biến môi trường (xem `.env.example`).
2. Mở `config/models.yaml`, đối chiếu từng tên model với danh sách hiện hành rồi sửa.
3. Điền `REPORT_EMAIL` trong `frontend/app.js` (cần cho việc đăng store).
4. Đọc điều khoản của Gemini API và OpenRouter (dùng dữ liệu, dùng thương mại) trước khi đăng store hoặc thu tiền.

## Triển khai miễn phí (ví dụ Render, kiểm tra lại điều kiện gói free hiện hành)
- Đưa thư mục này lên một repo GitHub riêng tư (không kèm khóa).
- Tạo Web Service: Build `pip install -r backend/requirements.txt`; Start
  `cd backend && uvicorn app.main:create_app_from_env --factory --host 0.0.0.0 --port $PORT`
- Environment: `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `TRUST_PROXY=1`.
- Gói free thường tạm ngủ khi lâu không dùng nên lần mở đầu có thể chậm.

## Cài lên Android
Mở địa chỉ HTTPS của app bằng Chrome, chọn menu ⋮ rồi "Cài đặt ứng dụng" hoặc "Thêm vào màn hình chính".
iPhone: Safari, nút Chia sẻ, "Thêm vào Màn hình chính".

## Giới hạn đã biết
- Bộ đếm lượt nằm trong bộ nhớ (reset khi khởi động lại, chỉ đúng với một bản server); chưa có giới hạn theo phút.
- Lịch sử chat và nút "Hữu ích/Chưa tốt" chỉ lưu trên máy người dùng (localStorage), chưa gửi về server.
- Câu trả lời hiển thị dạng văn bản thuần, chưa định dạng Markdown.
