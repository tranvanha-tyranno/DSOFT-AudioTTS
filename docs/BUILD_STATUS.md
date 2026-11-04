# Trạng thái bàn giao — 04/11/2026

## Mã nguồn

- Firmware ESP-IDF C++: `app_main.cpp` giữ luồng khởi động/vòng lặp; HTTP/JSON, audio, WiFi và OTA nằm ở các module riêng trong `main/`.
- Cấu hình trực tiếp bằng C++ trong `main/speaker_config.h`: WiFi, server/token, GPIO, buffer và OTA. Đã bỏ menu riêng và `main/Kconfig.projbuild` của loa.
- Điểm vào IDE: `AudioWifiTTS.code-workspace`; hướng dẫn mới: `docs/DOC_CODE_TU_DAU.md`.
- Target **ESP32-S3**, ESP-IDF v5.5.5 đang cài tại `C:\Espressif\frameworks\esp-idf-v5.5.5`; I2S GPIO15/16/7, console UART0 và USB Serial/JTAG.
- Baseline 4 MB flash, chưa bật PSRAM; cấu hình flash/PSRAM cần khớp module thực tế.
- Backend điều phối: `backend/app.py`; đầu nối TTS: `backend/tts.py`; OpenAPI: `docs/openapi.json`.
- Dashboard web: `backend/static/`; API quản trị và cấu hình bền: `backend/dashboard.py`; mở demo bằng `scripts/dashboard.ps1`, cổng 8088.
- API TTS thật, khóa nhà cung cấp, WiFi, token thiết bị và PoP bàn giao đều để trống.

## Kiểm tra đã thực hiện

| Kiểm tra | Kết quả |
|---|---|
| ESP32-S3 / ESP-IDF 5.5.5 | PASS: tạo image esp32s3, BIN 941.152 byte, còn 52% partition |
| Kiểm tra file BIN bằng esptool | PASS: checksum và validation hash hợp lệ |
| Kiểm tra công thức volume khi biên dịch | PASS: 4 static_assert cho mẫu âm/dương, âm lượng 0 và 100%; đã sửa phép nhân có dấu |
| Cấu hình target, compiler và GPIO I2S | PASS: esp32s3, xtensa-esp32s3-elf-g++, GPIO15/16/7; có kiểm tra GPIO/trùng chân khi biên dịch |
| Backend: `python -m pytest backend/tests -q` | PASS: 24 tests, gồm helper lấy link đăng nhập Docker |
| Docker image / Compose | PASS: build có FFmpeg, chạy UID 10001, root filesystem chỉ đọc, healthcheck healthy |
| Luồng API trong Docker | PASS: nghe thử WAV 24 kHz, tải PCM 48.000 byte, ACK played; giữ khóa/cấu hình/lịch sử sau restart và tạo lại container với cùng volume |
| Nội dung Docker image | PASS: không chứa firmware, dữ liệu/token local hoặc thư mục test |
| Xuất `app.openapi()` | PASS: `docs/openapi.json`, 12 đường dẫn API |
| Workspace/settings/tasks JSON và liên kết trong README | PASS |
| Playwright trên Chrome: desktop 1440px và mobile 390px | PASS: lưu TTS, che API key, reload cấu hình, nghe WAV, gửi queue, đăng ký loa, phục hồi đăng nhập |
| Luồng web → backend → thiết bị kiểm thử mô phỏng → ACK | PASS: tải đúng PCM 48.000 byte; kết quả hiện trong lịch sử. Không phải thử board thật |

Các test backend kiểm tra luồng queue → tải binary → ACK, idempotency/conflict, ưu tiên/FIFO, xác thực/cách ly thiết bị, queue/rate limit, trạng thái sau restart/hết lease, TTS chưa cấu hình, tách WAV header/kiểm tra độ dài PCM, lưu/xóa/che khóa TTS, migration SQLite cũ, template JSON/header, đăng ký loa và session cookie.

## Cần người phát triển tiếp xác minh

Chưa nạp ESP32, chưa thử âm thanh thật/provisioning/OTA, chưa ghép API TTS của người dùng, chưa đo latency hoặc chạy soak. Các tiêu chí trong `PLAN_P01.md` là mục tiêu đề xuất. Không dùng kết quả compile/backend test làm bằng chứng nghiệm thu thiết bị.

Firmware dừng khi URL/token rỗng: điền trực tiếp trong `main/speaker_config.h` rồi build/nạp lại. WiFi/server không đọc các macro `CONFIG_SPEAKER_*` cũ. `sdkconfig`/`sdkconfig.h` chỉ phục vụ cấu hình nền tảng ESP-IDF. Các thư mục `build*`, log và `sdkconfig.buildcheck*` là dữ liệu kiểm tra, không phải cấu hình triển khai.

Build của target cũ được giữ trong `build-esp32-backup-*`; cấu hình cũ ở `sdkconfig.esp32.bak`. Không dùng các file BIN trong thư mục backup để nạp S3. Audio hiện dùng DOUT=7, BCLK=15, LRCK/WS=16, TX only và sample rate 24.000 Hz theo sơ đồ người dùng cung cấp; đã build lại thành công cho ESP32-S3.

Launcher dashboard tạo token operator/device riêng để demo và lưu tại `backend/data/demo_access.json`. API TTS thật vẫn chưa được điền. Dữ liệu kiểm thử trình duyệt nằm riêng ở `output/playwright/`, không đưa vào dashboard dùng thực.
