FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SPEAKER_DATA_DIR=/app/backend/data

WORKDIR /app

# FFmpeg chuyển MP3/WAV từ nhà cung cấp về PCM mà ESP32-S3 phát được.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 speaker \
    && useradd --uid 10001 --gid speaker --no-create-home speaker

COPY backend/requirements.txt /app/backend/requirements.txt
RUN python -m pip install --no-cache-dir -r backend/requirements.txt

COPY backend/*.py /app/backend/
COPY backend/static/ /app/backend/static/
RUN mkdir -p /app/backend/data && chown -R speaker:speaker /app/backend

USER speaker
EXPOSE 8088
VOLUME ["/app/backend/data"]

HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8088/health', timeout=2)"

# Một worker vì hàng đợi/cache của bản MVP dùng khóa trong process.
CMD ["python", "-m", "backend.demo", "--host", "0.0.0.0", "--port", "8088", "--no-browser"]
