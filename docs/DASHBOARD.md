# Dashboard web demo — DSOFT Voice Lab

## Chạy nhanh

Tại thư mục `AudioWifiTTS`:

```powershell
python -m pip install -r backend/requirements.txt
.\scripts\dashboard.ps1
```

Mặc định backend lắng nghe cổng **8088** trên các interface để ESP32 cùng LAN có thể truy cập. Dashboard tự mở tại `http://127.0.0.1:8088/`, đăng nhập bằng khóa operator riêng do launcher tạo. Giữ terminal chạy; Ctrl+C để dừng. Đổi cổng bằng `.\scripts\dashboard.ps1 -Port 8090`.

Launcher lưu khóa demo tại `backend/data/demo_access.json`; dữ liệu SQLite và cache nằm trong cùng thư mục, đã được loại khỏi git. Dashboard tạo session cookie HttpOnly/SameSite Strict sau khi kết nối để mở tab mới mà không nhập lại khóa. Nếu chưa có phiên đăng nhập, dùng `operator_key` trong file này hoặc chạy lại lệnh demo để mở trang đã kết nối. Nếu bạn tự đặt `SPEAKER_API_KEY` thì dùng khóa đó.

Nếu chạy backend bằng uvicorn như trước, `/` cũng có dashboard nhưng bạn cần nhập `SPEAKER_API_KEY` thủ công. Biến `SPEAKER_PUBLIC_URL` đặt URL/IP mà ESP32 truy cập được; launcher tự gợi ý IP LAN. Kiểm tra lại IP trong trang Kết nối ESP32 nếu máy có nhiều card mạng/VPN.

## 1. Cấu hình TTS

Chọn **API TTS của bạn**, nhập:

- **URL API:** endpoint HTTPS nhận POST và trả binary audio.
- **Khóa API:** nhập khi thêm mới/đổi khóa. Để trống giữ nguyên khóa cũ; đánh dấu “Xóa khóa đã lưu” nếu muốn bỏ khóa.
- **Voice ID / Model:** thông tin của dịch vụ, được chèn vào JSON qua biến tương ứng.
- **Định dạng:** PCM16 mono 24 kHz, WAV hoặc MP3. MP3 và WAV khác định dạng chuẩn cần `ffmpeg` trong PATH.
- **Nâng cao:** tên header, tiền tố và mẫu JSON. Mặc định là `Authorization: Bearer <key>`.

Mẫu JSON mặc định:

```json
{
  "text": "{{text}}",
  "voice": "{{voice}}",
  "format": "pcm_s16le",
  "sample_rate": 24000
}
```

Một hợp đồng khác có thể cần:

```json
{
  "input": { "text": "{{text}}" },
  "voice_id": "{{voice}}",
  "model_id": "{{model}}"
}
```

Ví dụ dịch vụ nhận `xi-api-key: <key>`: đặt tên header `xi-api-key`, để tiền tố trống. URL chứa Voice ID thì tự điền ID vào URL; chỉ các giá trị trong JSON được thay biến. Các biến được thay trên dữ liệu JSON nên dấu nháy/tiếng Việt trong câu không làm hỏng request.

Nhấn **Lưu cấu hình**. Cấu hình nằm trong SQLite và còn sau khi restart. Khóa nhà cung cấp không được trả về bởi API đọc cấu hình và không gửi xuống ESP32. Adapter này chưa tự đọc JSON chứa URL audio; trường hợp đó cần nâng cấp `backend/tts.py`.

Chọn **Âm mẫu** để kiểm tra web/backend/loa mà chưa gọi nhà cung cấp. Đó là beep 440 Hz một giây, không đọc câu bạn nhập. API thật vẫn để trống trong bản bàn giao.

## 2. Nghe thử và gửi tới ESP32

Nhập nội dung ở **Phát thử**:

- **Nghe thử trên web:** backend tạo/cache audio, bọc thành WAV để trình duyệt phát. Không tạo job cho ESP32.
- **Phát trên ESP32:** tạo job với device ID, nội dung, volume và mức ưu tiên. Bảng lịch sử theo dõi queued → playing → played/failed.

“Đang xử lý” bao gồm thời gian ESP32 nhận job, tải audio và phát. “Đã phát” chỉ hiển thị khi firmware gửi ACK. Nếu chưa có loa gọi về backend thì hiển thị “Chưa kết nối”, job tiếp tục chờ. Không giả lập thiết bị trong bản demo thật.

Trang cập nhật khoảng ba giây/lần; thiết bị được coi còn kết nối nếu đã gọi `/next` trong 15 giây gần nhất. Ưu tiên cao đi trước các câu chưa bắt đầu, không ngắt câu đang phát. Giới hạn hiện có: tối đa 20 job chờ/đang xử lý mỗi loa, 20 yêu cầu mới/phút/loa, 60 giây audio/câu.

## 3. Kết nối firmware

Trong **Kết nối ESP32**, chọn hoặc đăng ký `speaker-01`. Nếu không nhập token cho thiết bị mới, backend tạo token. Với thiết bị đã có, để trống giữ token cũ. Bấm **Sao chép code cấu hình C++** và thay các dòng server tương ứng trong `main/speaker_config.h`, bên trong `namespace speaker_config`.

```cpp
inline constexpr const char *wifi_ssid = "TEN_WIFI";
inline constexpr const char *wifi_password = "MAT_KHAU_WIFI";
inline constexpr const char *backend_url = "http://192.168.1.100:8088";
inline constexpr const char *device_id = "speaker-01";
inline constexpr const char *device_token = "TOKEN_TU_DASHBOARD";
inline constexpr bool allow_http_for_development = true;
```

Thay các giá trị ví dụ bằng thông tin thật. WiFi và server đọc trực tiếp từ code, không cần menuconfig.

Build và nạp lại firmware sau khi đổi cấu hình. `127.0.0.1`/`localhost` trên ESP32 là chính board, không phải máy tính; dùng URL LAN mà dashboard gợi ý. Firewall/mạng phải cho phép board truy cập cổng đã chọn; launcher không tự thay đổi firewall.

## Vị trí mã để nâng cấp

| Phần | File |
|---|---|
| Bố cục trang | `backend/static/index.html` |
| Màu sắc, responsive | `backend/static/style.css` |
| Nút bấm, request, cập nhật trạng thái | `backend/static/app.js` |
| API dashboard và lưu cấu hình | `backend/dashboard.py` |
| Sinh/chuyển định dạng audio | `backend/tts.py` |
| Hàng đợi dùng chung với ESP32 | `backend/app.py` |
| Mở demo, phát hiện IP, tạo khóa | `backend/demo.py`, `scripts/dashboard.ps1` |

Đây là backend MVP một process/worker. Việc tạo TTS giữ khóa xử lý chung nên provider chậm có thể làm dashboard phản hồi chậm; nếu dùng nhiều loa, bước tiếp theo là tách worker/outbox. Chưa xác nhận âm thanh, WiFi và OTA trên board thật.
