# Chạy backend/dashboard bằng Docker

Docker chạy cả API và giao diện web; không cần Node.js hay ESP-IDF trên máy chủ. Image có sẵn FFmpeg để chuyển MP3/WAV về PCM cho ESP32-S3.

Hợp đồng API và cấu hình: [API.md](API.md). Sau khi chạy, mở `/docs` cho API tích
hợp theo user_id, hoặc `/docs/internal` cho dashboard và ESP32.

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

## Server chỉ pull image đã build

Image: `ghcr.io/tranvanha-tyranno/dsoft-audiotts-backend:latest` cho máy chủ **Linux amd64/x86_64**. Workflow `Publish backend image` tự build/push khi mã backend thay đổi trên nhánh `main`; cũng có thể chạy thủ công trong tab Actions. Nếu package yêu cầu xác thực, đăng nhập GHCR theo hướng dẫn bên dưới.

Trên server, cập nhật code và cấu hình `.env` (chỉ cần sao chép file mẫu ở lần đầu):

```sh
git pull
# Lần đầu: cp .env.example .env
```

Trong `.env` điền ba dòng sau, thay IP/domain thật:

```dotenv
DASHBOARD_PORT=8088
SPEAKER_PUBLIC_URL=http://YOUR_SERVER_IP:8088
SPEAKER_IMAGE=ghcr.io/tranvanha-tyranno/dsoft-audiotts-backend:latest
```

Đăng nhập GHCR một lần bằng tài khoản có quyền đọc package. Khi Docker hỏi password, nhập **GitHub personal access token (classic)** có quyền `read:packages`, không phải mật khẩu GitHub:

```sh
docker login ghcr.io -u tranvanha-tyranno
docker compose pull backend
docker compose up -d --no-build backend
docker compose ps
docker compose exec backend python -m backend.access
```

Mỗi lần cập nhật image chỉ chạy lại hai lệnh `pull` và `up -d --no-build`; cấu hình và dữ liệu vẫn ở volume. Có thể thay `latest` bằng tag `sha-COMMIT_SHA` để chọn một bản cụ thể. Server không cần build image hoặc cài Python/FFmpeg riêng.

Build trên máy local bằng `docker compose build backend`, sau đó chạy `docker compose up -d --no-build`. Nếu `.env` local chưa có `SPEAKER_IMAGE`, Compose dùng `dsoft-audiotts-backend:local` như trước.

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
2. **Thiết bị:** lấy URL/token của container và chép code vào `main/speaker_config.local.h` trên máy build firmware. File riêng này không lên Git hoặc Docker image.
3. **Người dùng:** đăng ký user_id, lời chào và loa vào database.
4. **Phát theo ID:** chọn người dùng để nghe thử hoặc gửi lệnh tới board. Web gọi `/v1/detect` chỉ với user_id. Chọn Âm mẫu nếu chưa có TTS thật.

## Dữ liệu được giữ lại

Named volume `speaker-data` chứa:

- `speaker.sqlite3`: cấu hình TTS/device, hàng đợi và lịch sử.
- `demo_access.json`: khóa quản trị và khóa mặc định của lần tạo đầu tiên.
- `cache/`: audio PCM đã tạo.

`docker compose restart` hoặc `docker compose down` rồi `up -d` giữ volume. `docker compose down -v` sẽ xóa dữ liệu trong volume; không dùng lệnh đó nếu cần giữ cấu hình/lịch sử.

Docker volume và dữ liệu chạy Python local (`backend/data`) tách biệt. Cấu hình/token của hai bản có thể khác nhau. Dùng token do đúng dashboard đang kết nối cung cấp.

## Vận hành

### Khi phát thử báo HTTP 502

Backend khởi động thành công chưa chứng minh API TTS hoạt động. Bấm Phát thử rồi xem:

```sh
docker compose logs --since=5m --timestamps backend
```

Bản mới ghi `TTS provider rejected request: upstream_status=... code=...` và hiển thị
hướng xử lý ngay trên dashboard. `401` thường liên quan khóa; `400/422` là cấu hình
model/voice/JSON; `429` cần phân biệt hết số dư/hạn mức với giới hạn tốc độ. Không
ghi khóa, nội dung văn bản hoặc nguyên body lỗi từ nhà cung cấp vào log.

Nếu web báo 502 nhưng backend không ghi lỗi mới, kiểm tra reverse proxy và truy cập
trực tiếp cổng public trong `.env` (ví dụ `http://IP_THAT_CUA_SERVER:8090/`).
`SPEAKER_PUBLIC_URL` phải chứa IP/domain thật, không để nguyên chữ `IP_SERVER`.
Biến này dùng cho ESP32 tải âm thanh; nó không quyết định URL gọi API OpenAI.

Sau khi cập nhật image, làm mới trang bằng Ctrl+F5 trước khi thử lại.

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

Registry và token: [GitHub Container Registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry). Tùy chọn chạy image có sẵn: [docker compose up](https://docs.docker.com/reference/cli/docker/compose/up/).
