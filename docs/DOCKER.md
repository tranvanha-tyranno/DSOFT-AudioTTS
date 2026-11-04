# Chạy backend/dashboard bằng Docker

Docker chạy cả API và giao diện web; không cần Node.js hay ESP-IDF trên máy chủ. Image có sẵn FFmpeg để chuyển MP3/WAV về PCM cho ESP32-S3.

## Khởi động

Từ thư mục gốc repo `DSOFT-AudioTTS` (trên máy phát triển hiện tại là `AudioWifiTTS`):

```powershell
Copy-Item .env.example .env
```

Sửa `.env` theo máy chạy Docker:

```dotenv
DASHBOARD_PORT=8088
SPEAKER_PUBLIC_URL=http://192.168.1.100:8088
```

IP trên là ví dụ. Dùng IP LAN/domain thật mà ESP32 có thể truy cập. Không dùng IP bridge `172.x` của container, `localhost` hoặc `127.0.0.1` làm URL cho ESP32. Nếu đổi cổng public, đổi cả hai dòng cho khớp.

```sh
docker compose up -d --build
docker compose ps
```

Mở `http://IP_SERVER:8088/`. Chờ service có trạng thái `healthy`.

## Đăng nhập dashboard

Backend tự tạo khóa operator/device riêng trong volume ở lần khởi động đầu tiên. Trên Windows có thể mở ngay trang đã đăng nhập:

```powershell
.\scripts\docker-open.ps1
```

Trên Linux hoặc khi mở web ở máy khác:

```sh
docker compose exec backend python -m backend.access
```

Lệnh in đường dẫn đăng nhập cho người vận hành. Có thể đổi URL trong đường dẫn bằng tùy chọn `--url https://speaker.example.com/` nếu web đi qua reverse proxy.

Sau khi vào web:

1. **Cấu hình TTS:** nhập endpoint, khóa, voice/model, header/body và định dạng audio; bấm lưu.
2. **Kết nối ESP32:** lấy URL/token của container và chép code vào `main/speaker_config.h` trên máy build firmware.
3. **Phát thử:** nghe trên trình duyệt hoặc gửi tới board. Chọn Âm mẫu nếu chưa có TTS thật.

## Dữ liệu được giữ lại

Named volume `speaker-data` chứa:

- `speaker.sqlite3`: cấu hình TTS/device, hàng đợi và lịch sử.
- `demo_access.json`: khóa quản trị và khóa mặc định của lần tạo đầu tiên.
- `cache/`: audio PCM đã tạo.

`docker compose restart` hoặc `docker compose down` rồi `up -d` giữ volume. `docker compose down -v` sẽ xóa dữ liệu trong volume; không dùng lệnh đó nếu cần giữ cấu hình/lịch sử.

Docker volume và dữ liệu chạy Python local (`backend/data`) tách biệt. Cấu hình/token của hai bản có thể khác nhau. Dùng token do đúng dashboard đang kết nối cung cấp.

## Vận hành

```sh
docker compose logs --tail=100 -f backend
docker compose restart backend
docker compose up -d --build
docker compose down
```

Health endpoint: `/health`. Backend dùng một worker để phù hợp hàng đợi/khóa xử lý của bản MVP. Image chạy user UID 10001, root filesystem chỉ đọc, `/tmp` dùng tmpfs; dữ liệu ghi vào volume.

Code frontend thay đổi cần build lại image bằng `docker compose up -d --build`. Cấu hình TTS nhập trên dashboard không cần rebuild và vẫn còn sau khi restart. Với truy cập web qua Internet, đặt HTTPS/domain tại reverse proxy của máy chủ và cập nhật `SPEAKER_PUBLIC_URL`.

## File liên quan

| File | Vai trò |
|---|---|
| `backend/Dockerfile` | Python runtime, FFmpeg, non-root user, healthcheck |
| `compose.yaml` | Cổng public, named volume, restart, giới hạn log |
| `.dockerignore` | Chỉ gửi backend/static vào build context |
| `.env.example` | Mẫu địa chỉ/cổng public; `.env` thực không lên Git |
| `backend/access.py` | Đọc khóa đăng nhập từ môi trường/volume trong terminal quản trị |
| `scripts/docker-open.ps1` | Mở web Docker trên trình duyệt Windows |

Tham khảo: [Docker build best practices](https://docs.docker.com/build/building/best-practices/), [Compose readiness/healthcheck](https://docs.docker.com/compose/how-tos/startup-order/).
