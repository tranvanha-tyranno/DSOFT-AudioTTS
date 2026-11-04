# Nạp thử ESP32-S3 và kiểm tra dashboard

Firmware đã chuyển target sang **esp32s3**, dùng ESP-IDF 5.5.5. Code có WiFi, polling backend, audio I2S và ACK. Chưa xác nhận trên board thật. Cấu hình hiện tại vẫn cần WiFi và token đúng trước khi nạp để thử kết nối.

## 1. Nối MAX98357A

| ESP32-S3 | MAX98357A |
|---|---|
| GPIO15 | BCLK |
| GPIO16 | LRC / WS |
| GPIO7 | DIN |
| GND | GND |
| Nguồn theo module | VIN |

Đây là chân mặc định, đổi trực tiếp trong `main/speaker_config.h`. GPIO22–25 không tồn tại trên S3; GPIO26–32 thường dùng cho flash/PSRAM. Chừa GPIO19/20 cho USB native. Xem [GPIO ESP32-S3 của Espressif](https://docs.espressif.com/projects/esp-idf/en/v5.5.5/esp32s3/api-reference/peripherals/gpio.html).

Bạn có thể kiểm tra WiFi/backend trước khi gắn amp; kết quả phát âm thanh vẫn cần kiểm tra sau khi nối loa.

## 2. Mở backend và lấy cấu hình

Tại `AudioWifiTTS`, chạy:

```powershell
.\scripts\dashboard.ps1
```

Vào **Kết nối ESP32**, chọn `speaker-01`, lấy **URL backend trong LAN** và **Device token**. URL của ESP32 phải là IP của máy chủ, không phải `localhost` hay `127.0.0.1`. Board và máy tính cần truy cập được nhau qua mạng.

## 3. Sửa code WiFi và backend

Mở `main/speaker_config.h` và thay các chuỗi bằng thông tin của bạn:

```cpp
inline constexpr const char *wifi_ssid = "TEN_WIFI";
inline constexpr const char *wifi_password = "MAT_KHAU_WIFI";
inline constexpr const char *backend_url = "http://192.168.1.100:8088";
inline constexpr const char *device_id = "speaker-01";
inline constexpr const char *device_token = "TOKEN_TU_DASHBOARD";
inline constexpr bool allow_http_for_development = true;
```

URL trên chỉ là ví dụ; lấy IP LAN và token thực từ dashboard. Dùng WiFi 2,4 GHz. Không cần menuconfig. GPIO I2S trong cùng file phải khớp BCLK=15, WS=16, DOUT=7; `ota_url` để trống khi thử kết nối.

Nếu muốn nhập WiFi qua ESP SoftAP Prov, để `wifi_ssid` trống và đặt `provisioning_pop` ít nhất 8 ký tự trong cùng file.

Baseline đang dùng 4 MB flash và PSRAM tắt. Chưa biết mã module cụ thể nên chưa bật Octal flash/PSRAM. Thiết lập nền tảng của ESP-IDF vẫn phải khớp module thực tế trước khi nạp.

## 4. Build, nạp và xem log

```powershell
.\scripts\build.ps1
.\scripts\build.ps1 -Action flash -Port COM5
.\scripts\build.ps1 -Action monitor -Port COM5
```

Thay `COM5` bằng cổng thực của ESP32-S3. Không nạp file BIN cũ của ESP32 thường. Build mới tạo `build/dsoft_wifi_speaker.bin`; lệnh flash của ESP-IDF tự nạp bootloader, partition và application đúng offset cho S3.

Console UART0 được bật, cùng đầu ra phụ USB Serial/JTAG. Có thể dùng cổng USB-UART của board hoặc cổng USB native tương ứng để xem log. Nếu cổng native chưa xuất hiện hoặc không tự vào chế độ nạp, giữ BOOT, nhấn/thả RESET rồi thả BOOT và thử lại. Cáp cần truyền được dữ liệu.

## 5. Dấu hiệu kết nối thành công

Log dự kiến:

```text
speaker_main: DSOFT WiFi Speaker / ESP32-S3
speaker_wifi: Da co WiFi, IP: ...
speaker_main: Loa speaker-01 da san sang
speaker_api: Da ket noi backend (HTTP 204)
```

HTTP 204 là backend đang chờ câu mới. Nếu đã có câu thì HTTP 200 cũng là kết nối thành công. Dashboard sẽ hiện loa **Đang kết nối** sau một lượt cập nhật.

Trong **Cấu hình TTS**, chọn **Âm mẫu**, lưu rồi gửi một câu ở **Phát thử**. MAX98357A sẽ phát beep một giây và lịch sử chuyển **Đã phát** khi nhận ACK.

| Hiện tượng | Kiểm tra |
|---|---|
| Log yêu cầu sửa `speaker_config.h` | backend_url, device_id, device_token và cờ HTTP |
| Không có `Da co WiFi` | SSID/mật khẩu, mạng 2,4 GHz hoặc PoP provisioning |
| Có WiFi nhưng không kết nối backend | IP LAN/cổng 8088, server đang chạy, khả năng truy cập mạng/firewall |
| HTTP 401 | Device token không khớp dashboard; không dùng khóa operator/TTS cho firmware |
| Dashboard kết nối nhưng không có tiếng | Chân 15/16/7, nguồn amp, loa và volume; chọn Âm mẫu để thử trước |

API TTS thật chưa được cấu hình không cản việc thử kết nối WiFi/backend hoặc phát âm mẫu.
