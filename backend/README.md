# Backend — phần chạy trên máy chủ

**Tài liệu API và cấu hình:** xem [docs/API.md](../docs/API.md).
Đăng ký bằng `POST /v1/users`, gọi phát bằng `POST /v1/detect`, quản lý ở trang **Người dùng**.
Swagger tích hợp ở `/docs`; dashboard và firmware ở `/docs/internal`.

Không nạp thư mục này lên ESP32. Chạy Python tại thư mục gốc `AudioWifiTTS`.

**Vận hành bằng Docker:** làm theo [docs/DOCKER.md](../docs/DOCKER.md), chạy `docker compose up -d --build` từ gốc repo. Container có sẵn FFmpeg và giữ dữ liệu trong volume.

**Cách nhanh để demo:** chạy `.\scripts\dashboard.ps1`. Backend mở trên cổng 8088, trình duyệt tự kết nối dashboard. Bạn cấu hình TTS ngay trên web, không cần sửa biến môi trường cho mỗi lần đổi dịch vụ. Xem `docs/DASHBOARD.md`.

| File | Đọc khi cần |
|---|---|
| `app.py` | API nhận yêu cầu, xác thực, cache, SQLite, xếp hàng và báo trạng thái |
| `detection.py` | Đăng ký người dùng, ánh xạ mã loa và phát theo user_id |
| `api_docs.py` | Tách Swagger tích hợp và Swagger vận hành |
| `config.py` | Giới hạn văn bản và âm thanh dùng chung cho backend |
| `dashboard.py` | Lưu/đọc cấu hình TTS, đăng ký loa, nghe thử WAV, lịch sử và trạng thái kết nối |
| `static/` | Giao diện HTML/CSS/JavaScript, không cần npm build |
| `demo.py` | Khởi chạy demo và tạo khóa operator/device riêng trên máy |
| **`tts.py`** | **Ghép API TTS thật: hàm `synthesize()`**; đổi WAV/MP3 về PCM |
| `.env.example` | Tên các biến môi trường cần điền; URL/khóa TTS đang trống |
| `tests/test_api.py` | Các tình huống kiểm tra queue/ACK/xác thực/định dạng audio |

Trong `app.py`, đọc các phần đánh số: cấu hình → lưu trữ → xác thực → API. Các hàm nằm trong `create_app()` dùng chung cấu hình, kết nối SQLite và khóa xử lý của một instance backend.

## Ba bước khi ghép TTS

1. Điền thông tin trong trang **Cấu hình TTS**, hoặc đặt biến môi trường theo `.env.example` trước lần cấu hình đầu tiên. Cấu hình đã lưu trên dashboard được dùng khi khởi động lại.
2. Với API trả binary audio, chỉnh header/body ngay trên web. Mở **`tts.py → synthesize()`** nếu API có hợp đồng khác, ví dụ trả JSON chứa URL.
3. Đảm bảo kết quả sau chuẩn hóa là PCM16 little endian, mono, 24 kHz, dài tối đa 60 giây. Không sửa công thức phát trên ESP32 để “đoán” định dạng của nhà cung cấp.

TTS chưa cấu hình sẽ trả `503`. `TTS_PROVIDER=tone` chỉ tạo beep một giây để thử đường âm thanh, không đọc tiếng Việt.

## Chạy và kiểm thử

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
```

Nếu cần chạy bộ test: `.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt`.

Sau khi thiết lập biến môi trường:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --workers 1
.\.venv\Scripts\python.exe -m pytest backend/tests -q
```

Mở `http://127.0.0.1:8000/docs` để xem API. Bản MVP dùng một process/worker. Ví dụ đầy đủ về biến môi trường, gọi API bằng PowerShell, LAN/HTTPS và giới hạn hiện tại nằm trong [hướng dẫn kỹ thuật](../docs/HUONG_DAN_KY_THUAT.md).
