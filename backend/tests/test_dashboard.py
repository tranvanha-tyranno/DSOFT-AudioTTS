import io
import json
import sqlite3
import wave

from fastapi.testclient import TestClient
import httpx
import pytest

from backend.app import create_app
from backend import tts

OP = {"Authorization": "Bearer dashboard-operator-test-key"}
DEV = {"Authorization": "Bearer dashboard-device-test-key"}
DEVICES = {"speaker-01": "dashboard-device-test-key"}


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(tmp_path, "dashboard-operator-test-key", DEVICES.copy(), ""))


def test_static_dashboard_and_authentication(client):
    assert client.get("/").status_code == 200
    assert "Voice Lab" in client.get("/").text
    assert client.get("/assets/app.js").status_code == 200
    assert client.get("/assets/style.css").status_code == 200
    for url in ["/v1/dashboard/tts", "/v1/dashboard/overview", "/v1/dashboard/devices/speaker-01/connection"]:
        assert client.get(url).status_code == 401
        assert client.get(url, headers=DEV).status_code == 401


def test_save_key_mask_preserve_clear_and_restart(client, tmp_path):
    payload = {"provider": "http", "tts_url": "https://tts.example.test/speak", "api_key": "private-provider-key"}
    saved = client.put("/v1/dashboard/tts", headers=OP, json=payload)
    assert saved.status_code == 200
    assert saved.json()["has_api_key"] is True
    assert "private-provider-key" not in saved.text
    assert "tts_key" not in saved.json() and "api_key" not in saved.json()
    payload["api_key"] = ""
    assert client.put("/v1/dashboard/tts", headers=OP, json=payload).json()["has_api_key"] is True
    restarted = TestClient(create_app(tmp_path, "dashboard-operator-test-key", DEVICES.copy(), ""))
    settings = restarted.get("/v1/dashboard/tts", headers=OP).json()
    assert settings["provider"] == "http"
    assert settings["tts_url"] == payload["tts_url"]
    assert settings["has_api_key"] is True
    payload["clear_api_key"] = True
    assert restarted.put("/v1/dashboard/tts", headers=OP, json=payload).json()["has_api_key"] is False


@pytest.mark.parametrize("changes", [
    {"tts_url": "http://untrusted.test/speak"},
    {"body_template": {"message": "no text variable"}},
    {"auth_header": "bad\nheader"},
    {"auth_prefix": "Bearer\nInjected: value"},
])
def test_invalid_provider_configuration(client, changes):
    payload = {"provider": "http", "tts_url": "https://tts.example.test/speak", **changes}
    assert client.put("/v1/dashboard/tts", headers=OP, json=payload).status_code == 422


def test_preview_is_wav_and_does_not_enqueue(client, tmp_path):
    assert client.put("/v1/dashboard/tts", headers=OP, json={"provider": "tone"}).status_code == 200
    preview = client.post("/v1/dashboard/preview", headers=OP, json={"text": "Xin chào"})
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "audio/wav"
    with wave.open(io.BytesIO(preview.content), "rb") as audio:
        assert (audio.getframerate(), audio.getnchannels(), audio.getsampwidth(), audio.getnframes()) == (24000, 1, 2, 24000)
    assert client.get("/v1/dashboard/overview", headers=OP).json()["jobs"] == []
    assert client.post("/v1/dashboard/preview", headers=OP, json={"text": "Xin chào"}).content == preview.content
    assert len(list((tmp_path / "cache").glob("*.pcm"))) == 1


def test_dashboard_to_device_audio_ack_and_presence(client):
    client.put("/v1/dashboard/tts", headers=OP, json={"provider": "tone"})
    initial = client.get("/v1/dashboard/overview", headers=OP).json()
    assert initial["devices"][0]["online"] is False
    assert "dashboard-device-test-key" not in json.dumps(initial)
    queued = client.post("/v1/speak", headers={**OP, "Idempotency-Key": "web-demo-one"},
                         json={"device_id": "speaker-01", "text": "Chào từ dashboard", "volume": 45, "priority": 5})
    assert queued.status_code == 202
    overview = client.get("/v1/dashboard/overview", headers=OP).json()
    assert overview["totals"]["queued"] == 1
    assert overview["jobs"][0]["text"] == "Chào từ dashboard"
    assert overview["jobs"][0]["audio_kind"] == "test_tone"
    job = client.get("/v1/devices/speaker-01/next", headers=DEV).json()
    assert job["volume"] == 45
    audio = client.get(f"/v1/devices/speaker-01/audio/{job['id']}", headers=DEV, params={"lease": job["lease"]})
    assert len(audio.content) == job["audio_bytes"] == 48000
    result = client.post("/v1/devices/speaker-01/ack", headers=DEV,
                         json={"id": job["id"], "lease": job["lease"], "status": "played"})
    assert result.status_code == 200
    final = client.get("/v1/dashboard/overview", headers=OP).json()
    assert final["devices"][0]["online"] is True
    assert final["totals"]["played"] == 1
    assert final["jobs"][0]["status"] == "played"


def test_register_device_and_restart(client, tmp_path):
    assert client.put("/v1/dashboard/devices", headers=OP, json={"device_id": "new-speaker"}).status_code == 200
    connection = client.get("/v1/dashboard/devices/new-speaker/connection", headers=OP).json()
    assert len(connection["device_token"]) >= 16
    restarted = TestClient(create_app(tmp_path, "dashboard-operator-test-key", DEVICES.copy(), ""))
    auth = {"Authorization": f"Bearer {connection['device_token']}"}
    assert restarted.get("/v1/devices/new-speaker/next", headers=auth).status_code == 204
    assert restarted.put("/v1/dashboard/devices", headers=OP, json={"device_id": "new-speaker"}).status_code == 200
    assert restarted.get("/v1/dashboard/devices/new-speaker/connection", headers=OP).json()["device_token"] == connection["device_token"]


def test_existing_database_migration(tmp_path):
    with sqlite3.connect(tmp_path / "speaker.sqlite3") as con:
        con.execute("CREATE TABLE jobs(seq INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT UNIQUE,device TEXT,"
                    "request_key TEXT UNIQUE,fingerprint TEXT,audio TEXT,audio_bytes INTEGER,volume INTEGER,"
                    "priority INTEGER,status TEXT,created REAL,lease TEXT,expires REAL,updated REAL)")
        con.execute("INSERT INTO jobs(id,device,status,created,volume,priority) VALUES('old','speaker-01','played',1,70,0)")
    client = TestClient(create_app(tmp_path, "dashboard-operator-test-key", DEVICES.copy(), ""))
    overview = client.get("/v1/dashboard/overview", headers=OP).json()
    assert overview["jobs"][0]["id"] == "old"
    assert overview["jobs"][0]["text"] == ""
    assert overview["totals"]["played"] == 1


def test_http_template_auth_and_quoted_text(monkeypatch):
    captured = {}
    def respond(request):
        captured["json"] = json.loads(request.content)
        captured["key"] = request.headers["xi-api-key"]
        return httpx.Response(200, content=b"\x01\x00" * 240, headers={"Content-Type": "audio/pcm"})
    original_client = httpx.Client
    monkeypatch.setattr(tts.httpx, "Client", lambda **kwargs: original_client(transport=httpx.MockTransport(respond), **kwargs))
    text = 'Tiếng Việt: "xin chào" và giữ nguyên {{voice}}'
    audio = tts.synthesize(text, {"provider": "http", "tts_url": "https://tts.example.test/convert",
        "tts_key": "vendor-secret", "voice": "adam", "model": "model-vi", "format": "pcm",
        "auth_header": "xi-api-key", "auth_prefix": "", "body_template": {
            "input": {"text": "{{text}}"}, "voice": "{{voice}}", "model_id": "{{model}}"}})
    assert len(audio) == 480
    assert captured["json"] == {"input": {"text": text}, "voice": "adam", "model_id": "model-vi"}
    assert captured["key"] == "vendor-secret"


def test_dashboard_session_new_tab_and_logout(client):
    assert client.post("/v1/dashboard/session").status_code == 401
    session = client.post("/v1/dashboard/session", headers=OP)
    assert session.status_code == 200
    assert "httponly" in session.headers["set-cookie"].lower()
    assert "samesite=strict" in session.headers["set-cookie"].lower()
    # Một tab mới cùng trình duyệt gửi cookie, không cần đưa operator key vào JavaScript.
    assert client.get("/v1/dashboard/overview").status_code == 200
    # Session quản trị không được dùng để giả làm thiết bị.
    assert client.get("/v1/devices/speaker-01/next").status_code == 401
    assert client.get("/v1/dashboard/overview", headers={"Authorization": "Bearer wrong-key"}).status_code == 401
    assert client.delete("/v1/dashboard/session").status_code == 200
    assert client.get("/v1/dashboard/overview").status_code == 401
