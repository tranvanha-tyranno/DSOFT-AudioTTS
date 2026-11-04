# Kế hoạch P01 — Loa WiFi TTS với ESP-IDF

Ngày lập lại: **04/11/2026**. Nguồn: `C:\Users\tyranno\Documents\output\Ke_hoach_DSOFT_IoT_AI_8_section_theo_du_an_v3 (1).xlsx`, `01_Tong_quan!A10:K10`, `02_WBS_Cong_viec!A5:J16`, rủi ro `04_Rui_ro!A17:K17`.

## Mục tiêu và quyết định

Luồng nghiệm thu: ứng dụng/AI gửi văn bản tiếng Việt qua API có xác thực → backend gọi TTS/cache → ESP32 nhận một job → phát qua MAX98357A → backend nhận trạng thái hoàn tất/thất bại. Đầu vào API TTS để trống theo yêu cầu; chưa chọn hay gọi dịch vụ có tính phí.

Phần cứng mục tiêu: **ESP32-S3 + MAX98357A**. Phần mềm dùng **ESP-IDF thuần C++**, không phụ thuộc Arduino/dtg-arduino. Baseline dùng 4 MB flash, chưa bật PSRAM; chân I2S mặc định là GPIO15/16/7. Chọn lại cấu hình flash/PSRAM nếu module cụ thể yêu cầu.

Phân chia: ESP32 chịu trách nhiệm WiFi, TLS, buffer và I2S; backend chịu trách nhiệm OpenAPI, TTS, chuyển định dạng, cache và điều phối. Đường audio nội bộ dùng PCM16 mono 24 kHz: khoảng **48 KB/giây**; firmware nhân đôi thành stereo trên I2S. Buffer 32 KB chứa khoảng **0,68 giây**, prebuffer 12 KB khoảng **0,26 giây**; các mức này cần đo lại với WiFi thực.

## Lịch 10 ngày làm việc

Baseline đề xuất **04–17/11/2026**, thứ Hai–thứ Sáu, chưa trừ ngày nghỉ riêng. Đây là kế hoạch thực hiện/nghiệm thu, không phải tuyên bố mọi mục đã hoàn tất. Nếu một người làm cả firmware/backend, giữ thứ tự dưới đây; không coi các hạng mục dài là tự động chạy song song.

| Ngày | Công việc và liên hệ WBS gốc | Đầu ra / điều kiện chuyển bước |
|---|---|---|
| D1 · 04/11 | P01.01–03: khóa use case, ESP32/MAX98357A, API contract, NFR; tạo khung C++ | Sơ đồ, hợp đồng job/ACK, cấu hình còn trống được liệt kê |
| D2 · 05/11 | P01.04: đấu nối nguồn/loa; test I2S bằng PCM mẫu | Nghe được tone và PCM chuẩn, không reset do nguồn |
| D3 · 06/11 | P01.05: provisioning/NVS, reconnect, HTTPS và đồng hồ | Provision thành công; WiFi mất rồi trở lại tự kết nối |
| D4 · 09/11 | P01.06: stream producer/consumer, prebuffer, volume | Câu 1–60 giây phát đúng tốc độ, có lỗi khi stream bị cắt |
| D5 · 10/11 | P01.07: backend, Swagger, Bearer, rate limit, SQLite | Sai khóa bị chặn, queue bền sau restart, idempotency đạt |
| D6 · 11/11 | P01.08: ghép API TTS thực; chuẩn hóa PCM; cache | Câu tiếng Việt tạo/phát đúng; lần gọi trùng dùng cache; lỗi provider rõ |
| D7 · 12/11 | P01.09–10: ưu tiên/FIFO, ACK, gọi từ IoT/AI | Không phát chồng; queue đúng thứ tự; ACK không gây phát lại |
| D8 · 13/11 | P01.05/11: kiểm tra OTA, lỗi WiFi/TLS, nguồn, timeout | OTA có tăng version; thử rollback; audio lỗi chuyển failed |
| D9 · 16/11 | P01.11: benchmark và soak trên board | Có log thời gian/heap/dropout, lỗi được ghi và phân loại |
| D10 · 17/11 | P01.12: sửa lỗi quan trọng, UAT, đóng gói mã/config | Demo text → tiếng Việt → ACK; bàn giao sơ đồ và cách build |

Mã nền đã được chuẩn bị trong lần bàn giao này; D2–D10 vẫn cần thực thi/đối chiếu trên phần cứng và API thực tế. Ngày demo phụ thuộc việc có nguồn/loa hoạt động và thông tin API TTS trước D6.

## Tiêu chí nghiệm thu đề xuất, chưa phải số đo thực

- 20 câu tiếng Việt gồm dấu, số, ngày giờ: nghe hiểu đúng ở bộ câu đã chọn.
- 100 job nối tiếp: không phát chồng, không phát thêm vì gửi lại cùng Idempotency-Key; FIFO khi cùng mức ưu tiên.
- Volume 0/30/70/100 hoạt động; thông báo ưu tiên chỉ đổi thứ tự câu chưa bắt đầu.
- Với LAN ổn định/cache hit: P95 từ request đến mẫu âm thanh đầu tiên **≤ 2 giây**; cache miss **≤ 8 giây**, cần điều chỉnh sau đo nhà cung cấp. Đây là mục tiêu đề xuất.
- Mất WiFi 30 giây: tự nối lại trong **≤ 30 giây kể từ khi AP sẵn sàng**; job đang phát lỗi được ghi nhận, không tự lặp câu.
- Soak tối thiểu 8 giờ, ≥ 500 job: không panic/reset ngoài dự kiến; theo dõi minimum free heap, sai lệch đầu/cuối và số dropout, không có xu hướng rò bộ nhớ liên tục.
- Sai token/cross-device bị từ chối; queue vượt 20 hoặc >20 yêu cầu mới/phút bị giới hạn; payload không hợp lệ không làm treo board.
- OTA: download HTTPS, kiểm tra sai image/version, mất nguồn lúc tải, rollback khi boot thất bại. Chỉ đánh dấu đạt sau thử thật.

## Hợp đồng thiết bị

| Endpoint | Bên gọi / ý nghĩa |
|---|---|
| `POST /v1/speak` | Operator Bearer + Idempotency-Key; text/device/volume/priority → job ID |
| `GET /v1/jobs/{id}` | Operator xem queued/playing/played/failed |
| `GET /v1/devices/{id}/next` | Device Bearer nhận job + lease; 204 nếu chưa có hoặc còn job đang phát |
| `GET /v1/devices/{id}/audio/{job}?lease=...` | Device tải PCM của job đã được cấp lease |
| `POST /v1/devices/{id}/ack` | Device báo played/failed; retry ACK không thay đổi kết quả đã chốt |

Một lease tồn tại 180 giây; audio tối đa 60 giây, tải/phát giới hạn tổng thời gian 120 giây, ACK retry có giới hạn. Job đang phát bị mất nguồn/hết lease chuyển failed; người vận hành quyết định tạo yêu cầu mới. Không thể suy ra chắc chắn loa đã phát đủ từ một ACK bị mất.

## Rủi ro và phần nâng cấp

| Rủi ro / thiếu đầu vào | Hướng xử lý |
|---|---|
| API TTS chưa điền | Giữ adapter mẫu, test tone riêng; ghép `backend/tts.py → synthesize()` khi có hợp đồng API |
| WiFi gây hụt buffer | Đo bằng log, thử prebuffer lớn hơn; cân nhắc cache flash/SD và tải trước |
| Nguồn yếu gây reset/nhiễu | Kiểm tra sụt áp khi tăng volume, dây mass/nguồn amp, tụ theo module |
| TTS chậm chặn API MVP | Tách worker và outbox, queue Redis/MQTT khi mở rộng nhiều loa |
| Cache/SQLite tăng dần | Thêm TTL/quota và lịch dọn; bản đầu chưa tự dọn |
| Secrets trong speaker_config.h/binary | Dùng token riêng từng loa; phase production chuyển cấu hình NVS và quản lý khóa |

Ưu tiên nâng cấp sau mã nền: adapter TTS thật → test board/đo latency → telemetry/dropout → cache offline → worker nền/MQTT nếu cần độ trễ thấp → OTA ký image và cơ chế quản lý đội thiết bị. MP3 decoder trực tiếp trên ESP32, ngắt câu đang phát, microphone/STT và hội thoại hai chiều là phạm vi mở rộng.
