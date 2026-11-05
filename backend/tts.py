"""ĐẦU NỐI TTS — sửa synthesize() ở file này khi ghép API TTS thực tế.

text → nhà cung cấp tạo âm thanh → normalize_audio() → PCM16 mono 24 kHz.
provider trống: chưa cấu hình. tone: tiếng beep thử loa. http: adapter mẫu.
"""
from __future__ import annotations

import io
import json
import logging
import math
import re
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
from urllib.parse import urlparse
import wave

from fastapi import HTTPException
import httpx
from .config import MAX_AUDIO_BYTES, SAMPLE_RATE_HZ

RATE = SAMPLE_RATE_HZ
MAX_AUDIO = MAX_AUDIO_BYTES
logger = logging.getLogger("uvicorn.error")


def provider_failure(response: httpx.Response) -> HTTPException:
    """Chỉ đọc mã lỗi đã biết; không ghi body có thể chứa khóa hoặc văn bản."""
    body = bytearray()
    for chunk in response.iter_bytes(chunk_size=4096):
        body.extend(chunk)
        if len(body) > 16384:
            break
    try:
        data = json.loads(body)
        error = data.get("error", {}) if isinstance(data, dict) else {}
        if not isinstance(error, dict):
            error = {}
    except (ValueError, UnicodeError):
        error = {}
    known_codes = {
        "invalid_api_key", "insufficient_quota", "credit_balance_exhausted",
        "organization_spend_limit_exceeded", "project_spend_limit_exceeded",
        "organization_usage_limit_exceeded", "rate_limit_exceeded", "slow_down",
        "model_not_found", "invalid_request_error", "unsupported_country_region_territory",
    }
    code = next((value for value in (error.get("code"), error.get("type"))
                 if isinstance(value, str) and value in known_codes), "unknown")
    status = response.status_code
    if status == 401:
        message = "Khóa API TTS không hợp lệ hoặc đã bị thu hồi. Nhập lại khóa của nhà cung cấp."
    elif status == 403:
        message = "API TTS từ chối quyền truy cập. Kiểm tra quyền của khóa, model và giới hạn IP/khu vực."
    elif status == 429 and code in {
        "insufficient_quota", "credit_balance_exhausted", "organization_spend_limit_exceeded",
        "project_spend_limit_exceeded", "organization_usage_limit_exceeded",
    }:
        message = "Tài khoản API TTS hết số dư hoặc chạm hạn mức sử dụng. Kiểm tra Billing và Limits của nhà cung cấp."
    elif status == 429:
        message = "API TTS đang giới hạn yêu cầu. Đợi một lúc rồi thử lại; kiểm tra Limits nếu lỗi tiếp tục."
    elif status == 404 or code == "model_not_found":
        message = "Không tìm thấy URL API TTS hoặc model, hoặc khóa chưa có quyền dùng model đó."
    elif status in {400, 422}:
        message = "API TTS không chấp nhận cấu hình. Kiểm tra model, voice và JSON request."
        param = error.get("param")
        if isinstance(param, str) and param in {"model", "input", "voice", "response_format", "speed", "instructions"}:
            message += f" Trường cần kiểm tra: {param}."
    elif status >= 500:
        message = "Dịch vụ TTS hoặc proxy phía nhà cung cấp đang lỗi. Thử lại sau."
    else:
        message = "API TTS từ chối yêu cầu. Kiểm tra URL, khóa và JSON request."
    logger.warning("TTS provider rejected request: upstream_status=%s code=%s", status, code)
    return HTTPException(502, f"{message} (API HTTP {status}; code={code})")


def normalize_audio(data: bytes, fmt: str) -> bytes:
    """Chuẩn hóa file nhà cung cấp trả về thành dữ liệu ESP32 có thể phát."""
    if fmt == "pcm":
        pcm = data
    elif fmt == "wav":
        try:
            with wave.open(io.BytesIO(data), "rb") as source:
                if (source.getnchannels(), source.getsampwidth(), source.getframerate()) == (1, 2, RATE):
                    pcm = source.readframes(source.getnframes())
                else:
                    pcm = transcode(data)
        except (wave.Error, EOFError):
            raise HTTPException(502, "Invalid WAV from TTS")
    elif fmt == "mp3":
        pcm = transcode(data)
    else:
        raise HTTPException(503, "TTS_RESPONSE_FORMAT must be pcm, wav or mp3")
    if not pcm or len(pcm) % 2 or len(pcm) > MAX_AUDIO:
        raise HTTPException(502, "TTS must return 0 < duration <= 60s of PCM16 mono 24kHz")
    return pcm


def transcode(data: bytes) -> bytes:
    """Nhờ ffmpeg chuyển MP3/WAV khác định dạng sang PCM chuẩn."""
    executable = shutil.which("ffmpeg")
    if not executable:
        raise HTTPException(503, "Install ffmpeg to convert MP3/noncanonical WAV")
    # Limit output, run without a shell, and disable network protocols in the decoder.
    with tempfile.TemporaryDirectory(prefix="dsoft-audio-") as tmp:
        src, dst = Path(tmp) / "source.audio", Path(tmp) / "output.pcm"
        src.write_bytes(data)
        try:
            result = subprocess.run(
                [executable, "-nostdin", "-v", "error", "-protocol_whitelist", "file,pipe",
                 "-i", str(src), "-t", "61", "-f", "s16le", "-acodec", "pcm_s16le",
                 "-ar", str(RATE), "-ac", "1", str(dst)],
                capture_output=True, timeout=30, check=False,
            )
        except subprocess.TimeoutExpired:
            raise HTTPException(502, "Audio conversion timed out")
        if result.returncode or not dst.exists():
            raise HTTPException(502, "Unable to decode provider audio")
        return dst.read_bytes()


def synthesize(text: str, settings: dict) -> bytes:
    """NƠI GHÉP API TTS: đổi URL/header/body/response theo nhà cung cấp của bạn."""
    provider = settings["provider"]
    if provider == "tone":
        # Deliberately audible fixture; never presented as synthesized Vietnamese speech.
        return b"".join(struct.pack("<h", int(6000 * math.sin(2 * math.pi * 440 * i / RATE)))
                        for i in range(RATE))
    if provider != "http" or not settings["tts_url"]:
        raise HTTPException(503, "TTS API is not configured; set TTS_PROVIDER and TTS_URL")
    url = settings["tts_url"]
    if urlparse(url).scheme != "https":
        raise HTTPException(503, "TTS_URL requires HTTPS")
    prefix = settings.get("auth_prefix", "Bearer").strip()
    secret = settings["tts_key"]
    value = f"{prefix} {secret}" if prefix else secret
    headers = {settings.get("auth_header", "Authorization"): value} if secret else {}

    # Thay biến trên cấu trúc JSON, không ghép chuỗi JSON: dấu nháy trong văn bản vẫn hợp lệ.
    variables = {"text": text, "voice": settings["voice"], "model": settings.get("model", "")}

    def render_template(value):
        if isinstance(value, str):
            return re.sub(r"\{\{(text|voice|model)\}\}", lambda match: variables[match[1]], value)
        if isinstance(value, list):
            return [render_template(item) for item in value]
        if isinstance(value, dict):
            return {key: render_template(item) for key, item in value.items()}
        return value

    payload = render_template(settings.get("body_template", {
        "text": "{{text}}", "voice": "{{voice}}", "format": "pcm_s16le", "sample_rate": RATE,
    }))
    try:
        # No redirects: do not forward provider credentials to another origin.
        with httpx.Client(timeout=40, follow_redirects=False) as client:
            with client.stream("POST", url, headers=headers, json=payload) as response:
                if response.status_code != 200:
                    raise provider_failure(response)
                if "json" in response.headers.get("content-type", "").lower():
                    logger.warning("TTS provider returned JSON instead of binary audio")
                    raise HTTPException(502, "This adapter expects binary audio, not a JSON audio URL")
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > 12 * 1024 * 1024:
                        raise HTTPException(502, "TTS response too large")
                    chunks.append(chunk)
    except httpx.TimeoutException:
        logger.warning("TTS connection timed out after 40 seconds")
        raise HTTPException(502, "API TTS phản hồi quá chậm. Kiểm tra kết nối mạng của server và thử lại.") from None
    except httpx.HTTPError as error:
        logger.warning("TTS connection failed: error_type=%s", type(error).__name__)
        raise HTTPException(502, "TTS connection failed")
    return normalize_audio(b"".join(chunks), settings["format"])
