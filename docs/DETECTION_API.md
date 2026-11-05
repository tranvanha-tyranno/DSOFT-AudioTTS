# API nhận diện

Tài liệu đã được gộp tại **[API DSOFT Audio](API.md)** để dùng một bộ hướng dẫn thống nhất.

- Đăng ký: `POST /v1/users`.
- Phát từ database: `POST /v1/detect` với `{"user_id":1}`.
- Xem database: `GET /v1/users`.
- Xem ánh xạ loa: `GET /v1/device-aliases`.
- Swagger tích hợp: `/docs`.
- Swagger dashboard và ESP32: `/docs/internal`.

Các lệnh tích hợp dùng AdminKey của backend.
