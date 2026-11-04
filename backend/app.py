"""API ĐIỀU KHIỂN LOA — chạy trên máy chủ, không nạp lên ESP32.

Đọc theo thứ tự: mẫu request → cấu hình → SQLite → xác thực → các endpoint.
Phần gọi nhà cung cấp TTS/chuyển định dạng đã tách sang tts.py.
"""
from __future__ import annotations

import hashlib
from contextlib import contextmanager
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import time
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from .tts import RATE, synthesize
from .dashboard import register_dashboard

ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"
bearer = HTTPBearer(auto_error=False)


class SpeakRequest(BaseModel):
    """Ứng dụng gửi văn bản này cho backend để tạo một lượt phát."""
    device_id: str = Field(pattern=ID_PATTERN)
    text: str = Field(min_length=1, max_length=1000)
    volume: int = Field(default=70, ge=0, le=100)
    priority: int = Field(default=0, ge=0, le=10)


class AckRequest(BaseModel):
    """ESP32 gửi kết quả sau khi phát xong hoặc gặp lỗi."""
    id: str = Field(pattern=ID_PATTERN)
    lease: str = Field(pattern=ID_PATTERN)
    status: Literal["played", "failed"]


def create_app(data_dir: Path | None = None, api_key: str | None = None,
               devices: dict[str, str] | None = None, provider: str | None = None) -> FastAPI:
    # 1. CẤU HÌNH: đọc biến môi trường; xem danh sách tại .env.example.
    operator_key = api_key if api_key is not None else os.getenv("SPEAKER_API_KEY", "")
    device_keys = devices if devices is not None else json.loads(os.getenv("SPEAKER_DEVICES", "{}"))
    settings = {
        "provider": provider if provider is not None else os.getenv("TTS_PROVIDER", ""),
        "tts_url": os.getenv("TTS_URL", ""), "tts_key": os.getenv("TTS_API_KEY", ""),
        "voice": os.getenv("TTS_VOICE", "default"), "format": os.getenv("TTS_RESPONSE_FORMAT", "pcm"),
        "revision": os.getenv("TTS_REVISION", "1"),
    }
    root = Path(data_dir or os.getenv("SPEAKER_DATA_DIR", "backend/data"))
    root.mkdir(parents=True, exist_ok=True)
    cache = root / "cache"
    cache.mkdir(exist_ok=True)
    database = root / "speaker.sqlite3"
    lock = threading.RLock()
    rates: dict[str, list[float]] = {}

    # 2. LƯU TRỮ: SQLite giữ hàng đợi sau khi backend khởi động lại.
    @contextmanager
    def connect():
        con = sqlite3.connect(database, timeout=10)
        con.row_factory = sqlite3.Row
        try:
            with con:
                yield con
        finally:
            con.close()

    with connect() as con:
        con.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS jobs (
                seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
                device TEXT NOT NULL, request_key TEXT UNIQUE NOT NULL, fingerprint TEXT NOT NULL,
                audio TEXT NOT NULL, audio_bytes INTEGER NOT NULL, volume INTEGER NOT NULL,
                priority INTEGER NOT NULL, status TEXT NOT NULL, created REAL NOT NULL,
                lease TEXT, expires REAL, updated REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS queue ON jobs(device,status,priority DESC,seq);
        """)
    app = FastAPI(title="DSOFT P01 WiFi Speaker", version="0.1.0",
                  description="Text → TTS/cache → durable queue → ESP-IDF/I2S speaker")
    app.state.public_url = os.getenv("SPEAKER_PUBLIC_URL", "")

    # 3. XÁC THỰC: ứng dụng dùng khóa operator; mỗi loa dùng khóa device riêng.
    def credential(auth: HTTPAuthorizationCredentials | None) -> str:
        if not auth or auth.scheme.lower() != "bearer":
            raise HTTPException(401, "Bearer token required", headers={"WWW-Authenticate": "Bearer"})
        return auth.credentials

    def operator(request: Request, auth: HTTPAuthorizationCredentials | None = Depends(bearer)):
        if len(operator_key) < 16:
            raise HTTPException(503, "Configure SPEAKER_API_KEY (minimum 16 characters)")
        supplied = credential(auth) if auth else request.cookies.get("dsoft_dashboard", "")
        if not supplied:
            raise HTTPException(401, "Bearer token required", headers={"WWW-Authenticate": "Bearer"})
        if not hmac.compare_digest(supplied, operator_key):
            raise HTTPException(401, "Invalid operator token")

    def device_auth(device_id: str, auth: HTTPAuthorizationCredentials | None = Depends(bearer)):
        key = device_keys.get(device_id, "")
        supplied = credential(auth)
        if len(key) < 16 or not hmac.compare_digest(supplied, key):
            raise HTTPException(401, "Invalid device credentials")

    def limit(device_id: str):
        now = time.monotonic()
        entries = [t for t in rates.get(device_id, []) if now - t < 60]
        if len(entries) >= 20:
            raise HTTPException(429, "Maximum 20 new speech requests per device/minute",
                                headers={"Retry-After": "60"})
        rates[device_id] = entries + [now]

    def cached_audio(text: str) -> Path:
        """Một cache dùng chung cho nghe thử web và câu gửi tới ESP32. Gọi bên trong lock."""
        cache_input = {**settings, "text": text}
        cache_input.pop("tts_key", None)
        digest = hashlib.sha256(json.dumps(cache_input, sort_keys=True).encode()).hexdigest()
        audio = cache / f"{digest}.pcm"
        if not audio.exists():
            pcm = synthesize(text, settings)
            temp = cache / f"{digest}.tmp"
            temp.write_bytes(pcm)
            temp.replace(audio)
        return audio

    # 4. API: các đường dẫn bên dưới tương ứng các bước trong app_main.cpp.
    @app.get("/health")
    def health():
        return {"status": "ok", "tts_provider": settings["provider"] or "unconfigured"}

    @app.post("/v1/speak", status_code=202, dependencies=[Depends(operator)])
    def speak(request: SpeakRequest, response: Response,
              idempotency_key: str = Header(min_length=1, max_length=128)):
        """Ứng dụng: văn bản → TTS/cache → xếp hàng. Chưa có nghĩa là loa đã phát."""
        if request.device_id not in device_keys:
            raise HTTPException(404, "Unknown device")
        if not request.text.strip():
            raise HTTPException(422, "Text cannot be whitespace")
        fingerprint = hashlib.sha256(request.model_dump_json().encode()).hexdigest()
        key = hashlib.sha256((request.device_id + ":" + idempotency_key).encode()).hexdigest()
        # Bounded single-process demo: hold the lock across generation to coalesce duplicate requests.
        # A production worker pool/outbox is part of the next phase.
        with lock:
            with connect() as con:
                existing = con.execute("SELECT * FROM jobs WHERE request_key=?", (key,)).fetchone()
                if existing:
                    if existing["fingerprint"] != fingerprint:
                        raise HTTPException(409, "Idempotency key reused with a different payload")
                    response.status_code = 200
                    return {"id": existing["id"], "status": existing["status"], "duplicate": True}
                con.execute("UPDATE jobs SET status='failed',updated=? WHERE status='playing' AND expires<?",
                            (time.time(), time.time()))
                queued = con.execute("SELECT COUNT(*) FROM jobs WHERE device=? AND status IN ('queued','playing')",
                                     (request.device_id,)).fetchone()[0]
                if queued >= 20:
                    raise HTTPException(429, "Device queue is full")
            limit(request.device_id)
            audio = cached_audio(request.text)
            job_id = secrets.token_hex(16)
            now = time.time()
            with connect() as con:
                con.execute("""INSERT INTO jobs
                    (id,device,request_key,fingerprint,audio,audio_bytes,volume,priority,status,created,updated,text,audio_kind)
                    VALUES (?,?,?,?,?,?,?,?,'queued',?,?,?,?)""",
                    (job_id, request.device_id, key, fingerprint, audio.name, audio.stat().st_size,
                     request.volume, request.priority, now, now, request.text,
                     "test_tone" if settings["provider"] == "tone" else "speech"))
            return {"id": job_id, "status": "queued", "duplicate": False,
                    "audio_kind": "test_tone" if settings["provider"] == "tone" else "speech"}

    @app.get("/v1/devices/{device_id}/next", dependencies=[Depends(device_auth)])
    def next_job(device_id: str):
        """ESP32: nhận một câu và mã lease. 204 nghĩa là hiện chưa có câu mới."""
        with lock, connect() as con:
            now = time.time()
            con.execute("INSERT INTO device_presence(device,last_seen) VALUES (?,?) "
                        "ON CONFLICT(device) DO UPDATE SET last_seen=excluded.last_seen", (device_id, now))
            # An interrupted playback is ambiguous. Expire as failed, never auto-requeue.
            con.execute("UPDATE jobs SET status='failed',updated=? WHERE device=? AND status='playing' AND expires<?",
                        (now, device_id, now))
            if con.execute("SELECT 1 FROM jobs WHERE device=? AND status='playing'", (device_id,)).fetchone():
                return Response(status_code=204)
            job = con.execute("SELECT * FROM jobs WHERE device=? AND status='queued' ORDER BY priority DESC,seq LIMIT 1",
                              (device_id,)).fetchone()
            if not job:
                return Response(status_code=204)
            lease = secrets.token_hex(16)
            con.execute("UPDATE jobs SET status='playing',lease=?,expires=?,updated=? WHERE id=?",
                        (lease, now + 180, now, job["id"]))
            return {"id": job["id"], "lease": lease, "volume": job["volume"],
                    "sample_rate": RATE, "audio_bytes": job["audio_bytes"], "lease_seconds": 180}

    @app.get("/v1/devices/{device_id}/audio/{job_id}", dependencies=[Depends(device_auth)])
    def audio_file(device_id: str, job_id: str, lease: str):
        """ESP32: tải PCM của câu đã được cấp quyền xử lý."""
        with lock, connect() as con:
            job = con.execute("SELECT * FROM jobs WHERE id=? AND device=?", (job_id, device_id)).fetchone()
            if not job:
                raise HTTPException(404, "Job not found")
            if job["status"] != "playing" or job["lease"] != lease or job["expires"] < time.time():
                raise HTTPException(409, "Lease invalid or expired")
            path = cache / job["audio"]
            if not path.exists():
                raise HTTPException(410, "Audio cache missing")
            return FileResponse(path, media_type="application/octet-stream",
                                headers={"Cache-Control": "no-store"})

    @app.post("/v1/devices/{device_id}/ack", dependencies=[Depends(device_auth)])
    def ack(device_id: str, request: AckRequest):
        """ESP32: xác nhận đã phát hoặc thất bại, không tạo lượt phát mới."""
        with lock, connect() as con:
            job = con.execute("SELECT * FROM jobs WHERE id=? AND device=?", (request.id, device_id)).fetchone()
            if not job:
                raise HTTPException(404, "Job not found")
            if job["lease"] != request.lease:
                raise HTTPException(409, "Stale lease")
            if job["status"] == request.status:
                return {"id": request.id, "status": request.status}
            if job["status"] != "playing" or job["expires"] < time.time():
                raise HTTPException(409, "Job already completed or lease expired")
            con.execute("UPDATE jobs SET status=?,updated=? WHERE id=?",
                        (request.status, time.time(), request.id))
            return {"id": request.id, "status": request.status}

    @app.get("/v1/jobs/{job_id}", dependencies=[Depends(operator)])
    def status(job_id: str):
        """Ứng dụng: xem queued / playing / played / failed."""
        with lock, connect() as con:
            con.execute("UPDATE jobs SET status='failed',updated=? WHERE id=? AND status='playing' AND expires<?",
                        (time.time(), job_id, time.time()))
            job = con.execute("SELECT id,device,status,volume,priority,created,updated FROM jobs WHERE id=?",
                              (job_id,)).fetchone()
            if not job:
                raise HTTPException(404, "Job not found")
            return dict(job)

    register_dashboard(app, operator_auth=operator, connect=connect, lock=lock,
                       settings=settings, device_keys=device_keys, cached_audio=cached_audio)
    return app


app = create_app()
