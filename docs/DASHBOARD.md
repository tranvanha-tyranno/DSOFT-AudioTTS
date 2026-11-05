# Dashboard web demo — DSOFT Voice Lab

Tài liệu API thống nhất: [API.md](API.md). Trang `/docs` dành cho tích hợp theo
user_id; `/docs/internal` dành cho cấu hình dashboard và giao tiếp ESP32.

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

## 2. Đăng ký người dùng và phát theo ID

Mở **Người dùng**, đăng ký `user_id`, tên hiển thị, lời chào và loa nhận lệnh.
Đăng ký dùng `POST /v1/users`; chỉnh sửa dùng `PUT /v1/users/{user_id}` với
body gồm `name`, `text_to_speech`, `device_id`. Lưu dữ liệu không tự phát loa.

Mở **Phát theo ID**, chọn người dùng đã đăng ký. Trang hiển thị đúng lời chào và
loa từ database, không có ô ghi đè nội dung hay đổi loa khi gọi phát.

- **Nghe thử trên web:** dùng lời chào của người dùng đang chọn, backend tạo/cache
  audio và bọc thành WAV. Không tạo job cho ESP32. Trình duyệt bỏ Blob URL khi nghe
  xong, đóng nghe thử, đổi người dùng, rời trang phát hoặc đăng xuất.
- **Phát trên loa:** gọi `POST /v1/detect` với body chỉ có `{"user_id":1}`. Backend
  lấy nội dung và loa từ database. Mỗi lần bấm tạo một lượt phát.
- Khung **Gọi từ ứng dụng của bạn** hiển thị URL hiện tại, JSON và lệnh cURL để sao
  chép. Lệnh dùng `YOUR_ADMIN_KEY` làm chỗ điền khóa, không chèn khóa thật vào mã mẫu.

Lịch sử theo dõi queued → playing → played/failed. “Loa đang xử lý” bao gồm tải và
phát. “Loa báo hoàn tất” chỉ xác nhận firmware gửi ACK sau khi ghi xong I2S, không
đo được âm thanh thực tế tại loa. Nếu loa offline, yêu cầu vẫn xếp hàng chờ kết nối.

Trang cập nhật trạng thái khoảng ba giây/lần, danh sách người dùng khoảng chín
giây/lần; thiết bị online nếu gọi `/next` trong 15 giây gần nhất. Mỗi lượt tối đa
1.000 ký tự và 60 giây audio; tối đa 20 job chờ/đang xử lý và 20 yêu cầu mới/phút/loa.

ESP32 tải PCM theo từng phần và phát song song. Bộ đệm 32 KiB chỉ được cấp khi có
job, giải phóng sau khi tác vụ tải và I2S đều dừng, kể cả khi gặp lỗi. Nếu tác vụ
I2S chưa dừng sau timeout, firmware giữ bộ đệm đó để tránh truy cập bộ nhớ đã giải
phóng; chỉ thu hồi khi tác vụ đã kết thúc. Monitor báo `Audio RAM allocated` và
`Audio RAM released: buffer=0 bytes`. ESP32 không ghi file WAV/PCM vào flash/SD.
Cache audio ở backend vẫn giữ để dùng lại; người dùng, khóa, cấu hình và lịch sử
không thay đổi bởi cơ chế giải phóng RAM.

## 3. Kết nối firmware

Trong **Thiết bị**, đăng ký `speaker-01` hoặc chọn loa đang có ở phần **Cấu hình
firmware**. Để trống token để tạo token cho loa mới hoặc giữ token của loa đã có.
Bấm **Xem cấu hình kết nối**, rồi **Sao chép cấu hình** và thay các dòng tương ứng
trong `main/speaker_config.local.h`. File này được include bên trong namespace
`speaker_config`, không thêm namespace lần nữa. Token được ẩn
khi rời trang Thiết bị hoặc bấm **Ẩn token**.

Phần **Mã loa từ hệ thống ngoài** dùng API `/v1/device-aliases`. Ví dụ mã `0001`
trỏ tới `speaker-01`, giúp đăng ký người dùng bằng mã ngoài mà không nạp lại board.

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
