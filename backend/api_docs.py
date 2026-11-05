"""Tài liệu tích hợp chỉ hiển thị API người dùng; vận hành có trang riêng."""
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi

from .config import MAX_AUDIO_SECONDS, MAX_TEXT_LENGTH

PUBLIC_TAGS = [
    {"name": "Phát âm thanh", "description": "Đã đăng ký người dùng: chỉ gửi user_id để lấy nội dung và loa từ database."},
    {"name": "Người dùng", "description": "Đăng ký, xem, cập nhật và xóa thông tin người dùng."},
    {"name": "Mã loa", "description": "Ánh xạ mã bên ngoài, ví dụ 0001, tới ID loa thực tế."},
    {"name": "Trạng thái", "description": "Theo dõi lượt phát và kiểm tra backend."},
]
INTERNAL_TAGS = [
    {"name": "ESP32", "description": "Firmware dùng DeviceToken của đúng loa để nhận job, tải PCM và gửi ACK."},
    {"name": "Dashboard", "description": "Dashboard dùng AdminKey để cấu hình TTS, nghe thử và quản lý loa."},
]


def configure_api_docs(app):
    public_names = {tag["name"] for tag in PUBLIC_TAGS}

    def public_schema():
        if app.openapi_schema is None:
            routes = [route for route in app.routes if public_names.intersection(getattr(route, "tags", []))]
            app.openapi_schema = get_openapi(
                title=app.title, version=app.version, routes=routes, tags=PUBLIC_TAGS,
                description=(
                    "API tích hợp của dự án DSOFT Audio.\n\n"
                    "1. Đăng ký bằng **POST /v1/users**.\n"
                    '2. Gọi **POST /v1/detect** với body **`{"user_id": 1}`**.\n'
                    "3. Xem kết quả bằng **GET /v1/jobs/{job_id}**.\n\n"
                    "Bấm **Authorize**, nhập khóa quản trị backend vào **AdminKey**. "
                    "Nội dung và loa được lấy từ database; mỗi lệnh tạo một lượt phát.\n\n"
                    f"Giới hạn: {MAX_TEXT_LENGTH} ký tự và {MAX_AUDIO_SECONDS} giây audio mỗi lượt. "
                    "`played` là xác nhận do firmware gửi sau khi xuất I2S, không phải phép đo âm thanh thực tế.\n\n"
                    "[Tài liệu vận hành dashboard và ESP32](/docs/internal)."
                ),
            )
        return app.openapi_schema

    app.openapi = public_schema

    @app.get("/openapi-internal.json", include_in_schema=False)
    def internal_schema():
        names = {tag["name"] for tag in INTERNAL_TAGS}
        routes = [route for route in app.routes if names.intersection(getattr(route, "tags", []))]
        return get_openapi(
            title="DSOFT Audio — vận hành", version=app.version, routes=routes, tags=INTERNAL_TAGS,
            description=("API cho dashboard và firmware hiện tại. Dashboard dùng AdminKey; "
                         "ESP32 dùng DeviceToken riêng của loa. [API tích hợp](/docs)."),
        )

    @app.get("/docs/internal", include_in_schema=False)
    def internal_docs():
        return get_swagger_ui_html(openapi_url="/openapi-internal.json", title="DSOFT Audio — API vận hành",
                                   swagger_ui_parameters={"defaultModelsExpandDepth": -1, "docExpansion": "list"})
