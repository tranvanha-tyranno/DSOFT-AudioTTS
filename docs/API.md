# API DSOFT Audio

## Mở đúng tài liệu

- **`/docs` — API tích hợp:** người dùng, phát theo user_id, mã loa và trạng thái job.
- **`/docs/internal` — API vận hành:** dashboard, cấu hình TTS và giao tiếp ESP32.
- **`/openapi.json`** và **`/openapi-internal.json`** là hai schema tương ứng.

Swagger dùng URL của trang đang mở để gọi API. Domain thật hay Cloudflare tạm đều
dùng cùng endpoint bên dưới; không cần sửa đường dẫn trong firmware cho từng user.

## Khóa và nơi cấu hình

| Thành phần | Dùng ở đâu | Lấy hoặc thiết lập ở đâu |
|---|---|---|
| **AdminKey** | API tích hợp và dashboard | Khóa quản trị backend; `python -m backend.access` hoặc `docker compose exec backend python -m backend.access` |
| **DeviceToken** | ESP32 nhận job, tải PCM, gửi ACK | Dashboard → Thiết bị; ghi vào `speaker_config.local.h` |
| **Khóa API TTS** | Backend gọi dịch vụ tạo giọng nói | Dashboard → Cấu hình TTS; lưu trong SQLite, không đưa vào firmware |

Trong `/docs`, bấm **Authorize** và nhập nguyên AdminKey. Swagger tự thêm `Bearer`.
Khi gọi từ ứng dụng khác, dùng header `Authorization: Bearer ADMIN_KEY`.
`/docs/internal` có hai ô Authorize riêng: AdminKey và DeviceToken.

## Luồng gọi tối thiểu

### 1. Ánh xạ mã loa nếu cần

Firmware đang dùng `speaker-01`, nhưng hệ thống bên ngoài dùng mã `0001`:

```http
PUT /v1/device-aliases/0001
Authorization: Bearer ADMIN_KEY
Content-Type: application/json

{"device_id": "speaker-01"}
```

### 2. Đăng ký thông tin vào database

```http
POST /v1/users
Authorization: Bearer ADMIN_KEY
Content-Type: application/json

{
  "user_id": 1,
  "name": "Anh Quý",
  "text_to_speech": "Xin chào anh Quý",
  "device_id": "0001"
}
```

`user_id` là số nguyên dương; `name` có thể bỏ trống. Thành công trả **201**.
Đăng ký chỉ lưu dữ liệu, chưa phát audio. ID đã tồn tại trả **409**; dùng PUT để sửa.
Loa được lưu bằng ID thực tế sau khi áp dụng ánh xạ.

### 3. Gọi phát chỉ bằng user_id

```http
POST /v1/detect
Authorization: Bearer ADMIN_KEY
Content-Type: application/json

{"user_id": 1}
```

Body chỉ có `user_id`. Backend luôn lấy nội dung và loa từ database.
Không có tham số `Idempotency-Key`, `device_id`, `text_to_speech` hoặc `Detect_person`
trong lệnh này. Hệ thống nhận diện gọi endpoint khi cần phát; mỗi lần gọi tạo một job.

Phản hồi **202**:

```json
{
  "id": "JOB_ID",
  "status": "queued",
  "user_id": 1,
  "device_id": "speaker-01",
  "text_to_speech": "Xin chào anh Quý"
}
```

`id` là mã lượt phát, không phải ID cần ghi vào firmware. ID người dùng chưa đăng ký
trả **404** và không tự tạo người dùng.

### 4. Theo dõi kết quả

```http
GET /v1/jobs/JOB_ID
Authorization: Bearer ADMIN_KEY
```

| Trạng thái | Ý nghĩa |
|---|---|
| `queued` | Audio đã được tạo/lấy từ cache, chờ loa nhận |
| `playing` | Job đã được giao cho loa bằng lease |
| `played` | Firmware gửi ACK sau khi hoàn tất xuất I2S |
| `failed` | Firmware báo lỗi hoặc lease hết hạn mà chưa có ACK |

**`played` không đo được âm thanh thực tế ở loa.** Ampli, nguồn hoặc dây loa có vấn đề
thì firmware vẫn có thể xuất I2S và gửi ACK. Dashboard dùng nhãn “Loa báo hoàn tất”.

## Danh sách API tích hợp

| Phương thức | Endpoint | Công dụng |
|---|---|---|
| POST | `/v1/detect` | Phát theo user_id đã đăng ký |
| POST | `/v1/users` | Đăng ký người dùng |
| GET | `/v1/users` | Danh sách người dùng: `{"users": [...]}` |
| GET | `/v1/users/{user_id}` | Thông tin một người dùng |
| PUT | `/v1/users/{user_id}` | Sửa name, text_to_speech, device_id; không gửi user_id trong body |
| DELETE | `/v1/users/{user_id}` | Xóa người dùng |
| GET | `/v1/device-aliases` | Danh sách ánh xạ: `{"device_aliases": [...]}` |
| PUT | `/v1/device-aliases/{alias}` | Lưu một ánh xạ mã loa |
| DELETE | `/v1/device-aliases/{alias}` | Xóa một ánh xạ |
| GET | `/v1/jobs/{job_id}` | Xem trạng thái lượt phát |
| GET | `/health` | Kiểm tra backend; endpoint này không cần khóa |

Các API dashboard và firmware nằm trong `/docs/internal`. Đường dẫn đang dùng của
ESP32 và dashboard được giữ để tương thích. API `/v1/speak` cho phép gửi văn bản
trực tiếp, có nội dung/volume/priority và khóa chống gửi trùng riêng. Web hiện tại
và tích hợp theo user_id dùng `/v1/detect`.

## Cấu hình và dữ liệu

- Docker đọc `.env` ở gốc repo: `DASHBOARD_PORT`, `SPEAKER_PUBLIC_URL`, `SPEAKER_IMAGE`.
- TTS, người dùng, loa và lịch sử lưu trong `SPEAKER_DATA_DIR/speaker.sqlite3`.
- Khóa quản trị mặc định lưu trong `SPEAKER_DATA_DIR/demo_access.json`.
- Audio cache lưu dạng PCM trong `SPEAKER_DATA_DIR/cache/`.
- `backend/.env.example` dành cho chạy Python thủ công; file này không tự được nạp.
- Cấu hình đã lưu từ dashboard được ưu tiên hơn cấu hình TTS ban đầu trong môi trường.

Các giới hạn chung nằm trong `backend/config.py`: **1.000 ký tự**, **60 giây**,
PCM16 mono **24 kHz**, tối đa **2.880.000 byte PCM** mỗi câu. Firmware hiện dùng cùng
giới hạn trong `main/speaker_config.h`. Nếu thay giới hạn âm thanh, cần cập nhật cả hai.
Cache được dùng lại khi cùng văn bản và cùng cấu hình TTS; bộ đệm RAM trên ESP32 là riêng.

## Mã lỗi thường gặp

| HTTP | Ý nghĩa |
|---|---|
| 401 | Thiếu hoặc sai loại khóa |
| 404 | Chưa đăng ký user_id, loa hoặc job |
| 409 | ID đã tồn tại hoặc xung đột thao tác |
| 422 | JSON sai hoặc có trường không được hỗ trợ |
| 429 | Hàng đợi đầy hoặc vượt giới hạn yêu cầu hiện tại |
| 502 | Gọi/tải/chuyển đổi TTS thất bại; xem `detail` và log backend |
| 503 | Khóa quản trị hoặc TTS chưa được cấu hình |

## Gọi từ PowerShell

```powershell
$apiBase = 'https://YOUR_BACKEND_DOMAIN'
$headers = @{ Authorization = "Bearer $env:SPEAKER_API_KEY" }
Invoke-RestMethod -Uri "$apiBase/v1/detect" -Method Post -Headers $headers `
    -ContentType 'application/json' -Body '{"user_id":1}'
```
