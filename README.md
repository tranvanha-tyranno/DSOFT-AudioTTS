# DSOFT-AudioTTS — Loa WiFi đọc văn bản

**Phần cứng:** ESP32-S3 + MAX98357A. **Firmware:** ESP-IDF C++ (`esp32s3`). **API TTS:** cấu hình trên dashboard.

**Tài liệu API:** [docs/API.md](docs/API.md). Đăng ký bằng `POST /v1/users`, phát từ
database bằng `POST /v1/detect` với `{"user_id":1}`. Swagger tích hợp ở `/docs`;
API dashboard và ESP32 ở `/docs/internal`.

**Chân loa mặc định trên S3:** GPIO15 → BCLK, GPIO16 → LRC/WS, GPIO7 → DIN. Hướng dẫn nạp và thử kết nối: [NAP_THU_ESP32S3.md](docs/NAP_THU_ESP32S3.md).

Ứng dụng gửi văn bản → backend tạo tiếng nói → ESP32 tải âm thanh → MAX98357A phát ra loa.

## Chạy web/backend bằng Docker

Sau khi clone repo, chạy các lệnh từ thư mục gốc `DSOFT-AudioTTS`:

```sh
cp .env.example .env
# Sửa IP LAN/domain và cổng public trong .env.
docker compose up -d --build
docker compose exec backend python -m backend.access
```

Trên PowerShell dùng `Copy-Item .env.example .env`. Lệnh `backend.access` in link đăng nhập dashboard. Trên Windows có thể chạy `.\scripts\docker-open.ps1` để tự mở web đã đăng nhập.

Docker gồm dashboard, API và FFmpeg; named volume giữ cấu hình TTS, token, hàng đợi và cache khi restart. Xem [hướng dẫn Docker](docs/DOCKER.md) để cấu hình IP/cổng và vận hành. Firmware ESP32-S3 vẫn build trên máy phát triển bằng ESP-IDF.

**Server chỉ pull rồi chạy:** đặt `SPEAKER_IMAGE=ghcr.io/tranvanha-tyranno/dsoft-audiotts-backend:latest` trong `.env`, đăng nhập `docker login ghcr.io`, sau đó chạy `docker compose pull backend` và `docker compose up -d --no-build backend`. Image private cho Linux amd64 được workflow **Publish backend image** build/push từ nhánh `main`. Chi tiết token và cấu hình server nằm trong [DOCKER.md](docs/DOCKER.md#server-chỉ-pull-image-đã-build).

## Mở dashboard web demo

Chạy từ `AudioWifiTTS`:

```powershell
.\scripts\dashboard.ps1
```

Dashboard mở tại **http://127.0.0.1:8088/** và tự kết nối bằng khóa demo riêng được tạo trên máy. Nếu thiếu thư viện: `python -m pip install -r backend/requirements.txt`. Trong VS Code cũng có task **P01: Mo dashboard web demo**.

1. **Cấu hình TTS:** chọn API của bạn, điền URL/khóa, voice/model và định dạng trả về. Có thể chỉnh header và JSON request; lưu cấu hình trước khi thử.
2. **Người dùng:** đăng ký user_id, lời chào và loa. Lưu dữ liệu không tự phát âm thanh.
3. **Phát theo ID:** chọn người dùng để nghe thử hoặc bấm **Phát trên loa**. Web gọi `POST /v1/detect` với body chỉ có `{"user_id":1}`; nội dung và loa lấy từ database.
4. **Thiết bị:** đăng ký loa, xem URL/token hoặc sao chép cấu hình C++ vào `main/speaker_config.local.h`. Với demo HTTP trong LAN, đặt `allow_http_for_development = true` rồi build/nạp.

ESP32 giữ luồng polling hiện có: backend tạo PCM → loa tải audio → I2S phát → gửi ACK. Nếu loa chưa kết nối, câu nằm ở trạng thái **Chờ loa**. **Âm mẫu** chỉ là beep một giây, không phải giọng nói TTS. Khóa API TTS nằm ở backend; dashboard không gửi khóa nhà cung cấp xuống board.

ESP32 không lưu file WAV/PCM trên flash/SD: cấp buffer RAM khi có job và giải phóng
sau khi tải/phát kết thúc, kể cả lỗi. Cache backend, người dùng, khóa và lịch sử
vẫn giữ. “Loa báo hoàn tất” là ACK của firmware, cần nghe thực tế để kiểm tra loa.

Chi tiết và ví dụ JSON: [hướng dẫn dashboard](docs/DASHBOARD.md).

## Mở dự án cho gọn

Mở **[AudioWifiTTS.code-workspace](AudioWifiTTS.code-workspace)** trong VS Code. Workspace này chỉ hiện dự án loa; thư mục build, log và cache được ẩn khỏi Explorer và tìm kiếm, vẫn còn trên đĩa.

## Đọc theo thứ tự này

1. **[app_main.cpp](main/app_main.cpp)** — chương trình bắt đầu ở đâu, khởi động và lặp làm gì.
2. **[speaker_config.h](main/speaker_config.h)** — cấu hình nằm ở đâu, chân I2S, buffer, thời gian chờ.
3. **[Đọc code từ đầu](docs/DOC_CODE_TU_DAU.md)** — giải thích từng bước bằng một câu ví dụ, các thuật ngữ và nơi sửa chức năng.

## Muốn sửa gì thì mở file nào?

| Bạn muốn sửa | Mở |
|---|---|
| Trình tự khởi động / vòng lặp chính | [main/app_main.cpp](main/app_main.cpp) |
| WiFi, URL backend, token | `main/speaker_config.local.h` — sao chép từ [file mẫu](main/speaker_config.local.h.example), không lên Git |
| Chân nối loa | [main/speaker_config.h](main/speaker_config.h) |
| Kích thước buffer / thời gian chờ | [main/speaker_config.h](main/speaker_config.h) |
| API ESP32 gọi backend | [main/speaker_api.cpp](main/speaker_api.cpp) |
| Âm lượng / phát I2S | [main/speaker_audio.cpp](main/speaker_audio.cpp) |
| Kết nối lại WiFi / nhập WiFi bằng ứng dụng | [main/speaker_network.cpp](main/speaker_network.cpp) |
| Cập nhật firmware qua mạng | [main/speaker_update.cpp](main/speaker_update.cpp) |
| Ghép API tạo giọng nói thực tế | **[backend/tts.py](backend/tts.py)** → hàm `synthesize()` |
| Xếp hàng / ưu tiên / trạng thái câu | [backend/app.py](backend/app.py) |
| Dashboard web | [backend/static/index.html](backend/static/index.html), `style.css`, `app.js` |
| API cấu hình dashboard | [backend/dashboard.py](backend/dashboard.py) |

## Cấu hình và build

Sao chép file mẫu rồi mở **`main/speaker_config.local.h`** để điền cấu hình riêng:

```powershell
Copy-Item main/speaker_config.local.h.example main/speaker_config.local.h
```

File này được include bên trong namespace `speaker_config`, không thêm namespace lần nữa.

```cpp
inline constexpr const char *wifi_ssid = "TEN_WIFI";
inline constexpr const char *wifi_password = "MAT_KHAU_WIFI";
inline constexpr const char *backend_url = "http://192.168.1.100:8088";
inline constexpr const char *device_id = "speaker-01";
inline constexpr const char *device_token = "TOKEN_TU_DASHBOARD";
```

Thay tên/mật khẩu WiFi, URL LAN và token bằng thông tin thực tế. Dashboard → Thiết bị
có nút **Sao chép cấu hình** để lấy URL, mã loa, token và cờ HTTP. GPIO sửa trong
`speaker_config.h`: BCLK=15, WS=16, DOUT=7. File `.local.h` không được đưa lên Git/Docker.

Trong workspace, **Ctrl+Shift+B** để build ESP32-S3. Task **P01: Mo code cau hinh WiFi - Server** mở thẳng file cấu hình.

Hoặc chạy tại thư mục `AudioWifiTTS`:

```powershell
.\scripts\build.ps1
```

Lưu `speaker_config.local.h`, build rồi nạp lại. WiFi/server nằm trong file riêng,
còn audio/OTA trong `speaker_config.h`. `sdkconfig`/`sdkconfig.h` dành cho nền tảng
ESP-IDF như chip, flash và console.

Chưa điền token thì firmware báo thiếu cấu hình khi boot. Chưa cấu hình TTS thì
backend chưa đọc được văn bản; chế độ `tone` chỉ phát beep thử loa. Đã kiểm tra
nạp ESP32-S3, nhận job và giải phóng RAM; cần nghe thực tế để nghiệm thu âm thanh.

## VS Code gạch đỏ ở dòng include?

Cấu hình IntelliSense có ở cả `DSOFT-data/.vscode/c_cpp_properties.json` (khi mở thư mục cha) và `AudioWifiTTS/.vscode/c_cpp_properties.json` (khi mở workspace riêng). Cả hai đọc `AudioWifiTTS/build/compile_commands.json`, nơi ESP-IDF ghi compiler và đường dẫn header thật. Không cần chép các thư viện ESP-IDF vào `main/`.

Sau khi đổi cấu hình, nếu VS Code còn hiển thị lỗi cũ: **Ctrl+Shift+P → Developer: Reload Window**. Nếu thư mục build chưa tồn tại thì chạy task build trước. Nếu cần kiểm tra cấu hình đang áp dụng: **C/C++: Log Diagnostics**, xem compiler phải là `xtensa-esp32s3-elf-g++` và compile commands phải trỏ về dự án loa.

Đọc tiếp khi cần: [hướng dẫn kỹ thuật và đấu dây](docs/HUONG_DAN_KY_THUAT.md), [cách chạy backend](backend/README.md), [kế hoạch](docs/PLAN_P01.md), [checklist phần cứng](docs/TEST_CHECKLIST.md), [trạng thái kiểm tra](docs/BUILD_STATUS.md).
