"""In đường dẫn đăng nhập dashboard từ khóa trong môi trường hoặc volume.

Docker: docker compose exec backend python -m backend.access
Không trả khóa trong API web công khai. Chỉ chạy lệnh này từ terminal quản trị.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.parse import quote


def access_info(url: str | None = None) -> dict[str, str]:
    key = os.getenv("SPEAKER_API_KEY", "")
    if not key:
        root = Path(os.getenv("SPEAKER_DATA_DIR") or str(Path(__file__).parent / "data"))
        path = root / "demo_access.json"
        if not path.exists():
            raise RuntimeError("Chưa có khóa. Khởi động backend trước.")
        key = json.loads(path.read_text(encoding="utf-8"))["operator_key"]
    if len(key) < 16:
        raise RuntimeError("Khóa operator chưa hợp lệ.")
    base = (url or os.getenv("SPEAKER_PUBLIC_URL") or "http://127.0.0.1:8088").rstrip("/") + "/"
    return {"dashboard_url": base, "operator_key": key,
            "login_url": base + "#key=" + quote(key, safe="")}


def main():
    parser = argparse.ArgumentParser(description="Mở phiên dashboard từ terminal quản trị")
    parser.add_argument("--url", help="URL web nếu dùng reverse proxy/cổng khác")
    parser.add_argument("--json", action="store_true", help="Dùng cho script mở trình duyệt")
    args = parser.parse_args()
    try:
        info = access_info(args.url)
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        parser.exit(1, f"{error}\n")
    print(json.dumps(info) if args.json else info["login_url"])


if __name__ == "__main__":
    main()
