"""Dashboard web: cấu hình TTS, xem loa, nghe thử và lịch sử phát.

Mọi API quản trị dùng khóa operator hiện có. Khóa nhà cung cấp chỉ lưu ở server.
"""
from __future__ import annotations

import io
import json
from pathlib import Path
import secrets
import time
from urllib.parse import urlparse
import wave

from fastapi import Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from .tts import RATE


class TTSUpdate(BaseModel):
    provider: str = Field(default="", pattern=r"^(|tone|http)$")
    tts_url: str = Field(default="", max_length=2048)
    api_key: str | None = Field(default=None, max_length=512)
    clear_api_key: bool = False
    voice: str = Field(default="default", min_length=1, max_length=160)
    model: str = Field(default="", max_length=160)
    format: str = Field(default="pcm", pattern=r"^(pcm|wav|mp3)$")
    auth_header: str = Field(default="Authorization", pattern=r"^[A-Za-z0-9-]{1,80}$")
    auth_prefix: str = Field(default="Bearer", max_length=80)
    body_template: dict = Field(default_factory=lambda: {
        "text": "{{text}}", "voice": "{{voice}}", "format": "pcm_s16le", "sample_rate": RATE,
    })

    @model_validator(mode="after")
    def validate_adapter(self):
        self.tts_url = self.tts_url.strip()
        if self.provider == "http":
            url = urlparse(self.tts_url)
            if url.scheme != "https" or not url.hostname or url.username or url.password:
                raise ValueError("URL TTS phải là HTTPS, không chứa username/password")
            if "{{text}}" not in json.dumps(self.body_template):
                raise ValueError("JSON gửi tới TTS cần có biến {{text}}")
        if len(json.dumps(self.body_template)) > 12000:
            raise ValueError("JSON cấu hình quá dài")
        if any(ord(c) < 32 or ord(c) > 126 for c in self.auth_prefix):
            raise ValueError("Tiền tố xác thực phải dùng ký tự ASCII hiển thị được")
        if self.api_key and any(ord(c) < 32 or ord(c) > 126 for c in self.api_key):
            raise ValueError("Khóa API phải dùng ký tự ASCII hiển thị được")
        return self


class DeviceUpdate(BaseModel):
    device_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    token: str = Field(default="", max_length=200)

    @model_validator(mode="after")
    def validate_token(self):
        if self.token and (len(self.token) < 16 or any(ord(c) < 33 or ord(c) > 126 for c in self.token)):
            raise ValueError("Device token cần 16–200 ký tự ASCII không có khoảng trắng")
        return self


class PreviewRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


def register_dashboard(app, *, operator_auth, connect, lock, settings, device_keys, cached_audio):
    """Nối giao diện vào đúng hàng đợi và cấu hình mà ESP32 đang dùng."""
    static = Path(__file__).parent / "static"
    app.mount("/assets", StaticFiles(directory=static), name="dashboard-assets")

    with connect() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS device_presence (device TEXT PRIMARY KEY, last_seen REAL NOT NULL);
        """)
        columns = {row[1] for row in con.execute("PRAGMA table_info(jobs)")}
        for name, declaration in [("text", "TEXT NOT NULL DEFAULT ''"),
                                  ("audio_kind", "TEXT NOT NULL DEFAULT 'speech'")]:
            if name not in columns:
                con.execute(f"ALTER TABLE jobs ADD COLUMN {name} {declaration}")
        saved = con.execute("SELECT value FROM app_settings WHERE key='tts'").fetchone()
        if saved:
            settings.update(json.loads(saved[0]))
        saved_devices = con.execute("SELECT value FROM app_settings WHERE key='devices'").fetchone()
        if saved_devices:
            device_keys.update(json.loads(saved_devices[0]))

    settings.setdefault("model", "")
    settings.setdefault("auth_header", "Authorization")
    settings.setdefault("auth_prefix", "Bearer")
    settings.setdefault("body_template", TTSUpdate().body_template)

    def persist(con, key, value):
        con.execute("INSERT INTO app_settings(key,value) VALUES (?,?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, json.dumps(value, ensure_ascii=False)))

    def public_settings():
        return {**{key: value for key, value in settings.items() if key != "tts_key"},
                "has_api_key": bool(settings.get("tts_key"))}

    @app.get("/", include_in_schema=False)
    def dashboard():
        return FileResponse(static / "index.html", headers={"Cache-Control": "no-store"})

    @app.post("/v1/dashboard/session", dependencies=[Depends(operator_auth)])
    def start_session(request: Request, response: Response):
        # Session cookie giúp mở tab mới mà không phải nhập lại khóa operator.
        header = request.headers.get("authorization", "")
        token = header.partition(" ")[2] if header else request.cookies.get("dsoft_dashboard", "")
        response.set_cookie("dsoft_dashboard", token, httponly=True, samesite="strict",
                            secure=request.url.scheme == "https", path="/")
        response.headers["Cache-Control"] = "no-store"
        return {"connected": True}

    @app.delete("/v1/dashboard/session", dependencies=[Depends(operator_auth)])
    def end_session(response: Response):
        response.delete_cookie("dsoft_dashboard", path="/", samesite="strict", httponly=True)
        return {"connected": False}

    @app.get("/v1/dashboard/tts", dependencies=[Depends(operator_auth)])
    def get_tts_settings():
        with lock:
            return public_settings()

    @app.put("/v1/dashboard/tts", dependencies=[Depends(operator_auth)])
    def save_tts_settings(request: TTSUpdate):
        with lock, connect() as con:
            values = request.model_dump(exclude={"api_key", "clear_api_key"})
            # Để trống ô API key: giữ khóa cũ. Chỉ xóa khi người dùng chọn rõ.
            secret = "" if request.clear_api_key else (request.api_key or settings.get("tts_key", ""))
            values["tts_key"] = secret
            values["revision"] = str(time.time_ns())
            persist(con, "tts", values)
            settings.update(values)
            return public_settings()

    @app.post("/v1/dashboard/preview", dependencies=[Depends(operator_auth)])
    def preview(request: PreviewRequest):
        if not request.text.strip():
            raise HTTPException(422, "Vui lòng nhập văn bản để nghe thử")
        with lock:
            pcm = cached_audio(request.text).read_bytes()
        output = io.BytesIO()
        with wave.open(output, "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(RATE)
            audio.writeframes(pcm)
        return Response(output.getvalue(), media_type="audio/wav", headers={"Cache-Control": "no-store"})

    @app.get("/v1/dashboard/overview", dependencies=[Depends(operator_auth)])
    def overview():
        with lock, connect() as con:
            now = time.time()
            con.execute("UPDATE jobs SET status='failed',updated=? WHERE status='playing' AND expires<?", (now, now))
            totals = dict(con.execute("SELECT status,COUNT(*) FROM jobs GROUP BY status").fetchall())
            seen = dict(con.execute("SELECT device,last_seen FROM device_presence").fetchall())
            devices = [{"id": device, "configured": len(token) >= 16,
                        "online": now - seen.get(device, 0) < 15, "last_seen": seen.get(device)}
                       for device, token in sorted(device_keys.items())]
            jobs = [dict(row) for row in con.execute(
                "SELECT id,device,text,status,volume,priority,created,updated,audio_kind "
                "FROM jobs ORDER BY seq DESC LIMIT 30")]
            return {"devices": devices, "jobs": jobs, "totals": totals,
                    "provider": settings["provider"], "server_time": now}

    @app.put("/v1/dashboard/devices", dependencies=[Depends(operator_auth)])
    def save_device(request: DeviceUpdate):
        with lock, connect() as con:
            token = request.token or device_keys.get(request.device_id) or secrets.token_urlsafe(24)
            updated = {**device_keys, request.device_id: token}
            persist(con, "devices", updated)
            device_keys.update(updated)
            return {"device_id": request.device_id, "configured": True}

    @app.get("/v1/dashboard/devices/{device_id}/connection", dependencies=[Depends(operator_auth)])
    def device_connection(device_id: str, request: Request):
        if device_id not in device_keys:
            raise HTTPException(404, "Không tìm thấy loa")
        # Endpoint quản trị riêng, khóa chỉ được tải khi người dùng mở phần kết nối.
        return {"device_id": device_id, "device_token": device_keys[device_id],
                "backend_url": app.state.public_url or str(request.base_url).rstrip("/"),
                "allow_http": (app.state.public_url or str(request.base_url)).startswith("http://")}
