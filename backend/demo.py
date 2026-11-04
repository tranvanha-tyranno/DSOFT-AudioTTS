"""Chạy `python -m backend.demo` để mở dashboard và backend dùng chung mạng với ESP32."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import socket
import threading
from urllib.parse import quote
import webbrowser

import uvicorn


def lan_ip() -> str:
    connection = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # UDP connect chỉ chọn route/interface, không gửi gói dữ liệu.
        connection.connect(("192.0.2.1", 9))
        return connection.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description="DSOFT Voice Lab dashboard")
    parser.add_argument("--host", default="0.0.0.0", help="Địa chỉ lắng nghe; mặc định cho ESP32 truy cập qua LAN")
    parser.add_argument("--port", type=int, default=8088)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    data = Path(os.getenv("SPEAKER_DATA_DIR") or str(Path(__file__).parent / "data")).resolve()
    data.mkdir(parents=True, exist_ok=True)
    access_file = data / "demo_access.json"
    if access_file.exists():
        access = json.loads(access_file.read_text(encoding="utf-8"))
    else:
        access = {"operator_key": secrets.token_urlsafe(32),
                  "devices": {"speaker-01": secrets.token_urlsafe(24)}}
        access_file.write_text(json.dumps(access, indent=2), encoding="utf-8")

    if not os.getenv("SPEAKER_API_KEY"):
        os.environ["SPEAKER_API_KEY"] = access["operator_key"]
    if not os.getenv("SPEAKER_DEVICES"):
        os.environ["SPEAKER_DEVICES"] = json.dumps(access["devices"])
    os.environ["SPEAKER_DATA_DIR"] = str(data)
    ip = args.host if args.host not in {"0.0.0.0", "127.0.0.1"} else lan_ip()
    if not os.getenv("SPEAKER_PUBLIC_URL"):
        os.environ["SPEAKER_PUBLIC_URL"] = f"http://{ip}:{args.port}"
    local_url = f"http://127.0.0.1:{args.port}/"
    print(f"Dashboard: {local_url}", flush=True)
    print(f"ESP32 backend: {os.environ['SPEAKER_PUBLIC_URL']}", flush=True)
    print("Mo Cau hinh TTS tren dashboard de thiet lap/kiem tra dich vu.", flush=True)
    print(f"Khoa quan tri demo duoc luu tai: {access_file}", flush=True)
    if not args.no_browser:
        # Khóa chỉ nằm trong fragment của trang mở cục bộ; app.js xóa fragment sau khi đọc.
        url = local_url + "#key=" + quote(os.environ["SPEAKER_API_KEY"], safe="")
        timer = threading.Timer(1.5, lambda: webbrowser.open(url))
        timer.daemon = True
        timer.start()
    uvicorn.run("backend.app:app", host=args.host, port=args.port, workers=1, access_log=False)


if __name__ == "__main__":
    main()
