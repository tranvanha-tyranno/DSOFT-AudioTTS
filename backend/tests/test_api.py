import io
import sqlite3
import wave

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from backend.app import create_app
from backend.tts import normalize_audio

OP = {"Authorization": "Bearer operator-key-for-tests"}
DEV = {"Authorization": "Bearer speaker-device-key-tests"}
KEYS = {"speaker-01": "speaker-device-key-tests", "speaker-02": "other-device-key-tests"}


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(tmp_path, "operator-key-for-tests", KEYS, "tone"))


def speak(client, key="one", **changes):
    payload = {"device_id": "speaker-01", "text": "Xin chào", **changes}
    return client.post("/v1/speak", headers={**OP, "Idempotency-Key": key}, json=payload)


def claim(client):
    response = client.get("/v1/devices/speaker-01/next", headers=DEV)
    assert response.status_code == 200
    return response.json()


def ack(client, job, **changes):
    return client.post("/v1/devices/speaker-01/ack", headers=DEV,
                       json={"id": job["id"], "lease": job["lease"], "status": "played", **changes})


def test_full_audio_and_idempotent_ack(client):
    queued = speak(client)
    assert queued.status_code == 202
    job = claim(client)
    assert job["id"] == queued.json()["id"]
    audio = client.get(f"/v1/devices/speaker-01/audio/{job['id']}",
                       params={"lease": job["lease"]}, headers=DEV)
    assert audio.status_code == 200
    assert len(audio.content) == job["audio_bytes"] == 48000
    assert client.get("/v1/devices/speaker-01/next", headers=DEV).status_code == 204
    assert ack(client, job).status_code == 200
    assert ack(client, job).status_code == 200
    assert ack(client, job, status="failed").status_code == 409
    assert client.get(f"/v1/jobs/{job['id']}", headers=OP).json()["status"] == "played"
    assert client.get("/v1/devices/speaker-01/next", headers=DEV).status_code == 204


def test_retry_and_conflicting_idempotency(client):
    first = speak(client)
    retry = speak(client)
    assert retry.status_code == 200
    assert retry.json()["id"] == first.json()["id"]
    assert speak(client, text="Câu khác").status_code == 409


def test_priority_then_fifo(client):
    low = speak(client, "low", priority=1).json()["id"]
    high1 = speak(client, "high1", priority=9).json()["id"]
    high2 = speak(client, "high2", priority=9).json()["id"]
    for expected in [high1, high2, low]:
        job = claim(client)
        assert job["id"] == expected
        assert ack(client, job).status_code == 200


def test_auth_and_device_isolation(client):
    assert client.post("/v1/speak", json={"text": "x", "device_id": "speaker-01"}).status_code == 401
    assert client.get("/v1/devices/speaker-01/next", headers=OP).status_code == 401
    assert client.get("/v1/devices/speaker-02/next", headers=DEV).status_code == 401
    job = claim_after_enqueue(client)
    assert ack(client, job, lease="incorrect").status_code == 409
    assert client.get(f"/v1/devices/speaker-02/audio/{job['id']}",
                       params={"lease": job["lease"]},
                       headers={"Authorization": "Bearer other-device-key-tests"}).status_code == 404


def claim_after_enqueue(client):
    assert speak(client).status_code == 202
    return claim(client)


def test_queue_bound_and_validation(client):
    assert speak(client, "blank", text="   ").status_code == 422
    assert speak(client, "volume", volume=101).status_code == 422
    assert speak(client, "unknown", device_id="missing").status_code == 404
    for i in range(20):
        assert speak(client, str(i)).status_code == 202
    assert speak(client, "overflow").status_code == 429


def test_rate_limit_after_queue_is_drained(client):
    for i in range(20):
        assert speak(client, str(i)).status_code == 202
        assert ack(client, claim(client)).status_code == 200
    assert speak(client, "over-rate").status_code == 429


def test_restart_and_expired_lease_do_not_replay(tmp_path):
    client = TestClient(create_app(tmp_path, "operator-key-for-tests", KEYS, "tone"))
    job = claim_after_enqueue(client)
    with sqlite3.connect(tmp_path / "speaker.sqlite3") as con:
        con.execute("UPDATE jobs SET expires=0 WHERE id=?", (job["id"],))
    restarted = TestClient(create_app(tmp_path, "operator-key-for-tests", KEYS, "tone"))
    assert restarted.get("/v1/devices/speaker-01/next", headers=DEV).status_code == 204
    assert restarted.get(f"/v1/jobs/{job['id']}", headers=OP).json()["status"] == "failed"
    assert ack(restarted, job).status_code == 409
    assert speak(restarted).json()["id"] == job["id"]


def test_unconfigured_tts_is_explicit(tmp_path):
    client = TestClient(create_app(tmp_path, "operator-key-for-tests", KEYS, ""))
    assert speak(client).status_code == 503
    assert client.get("/v1/devices/speaker-01/next", headers=DEV).status_code == 204


def test_pcm_validation_and_wav_header_removed():
    raw = b"\x01\x00" * 240
    buf = io.BytesIO()
    with wave.open(buf, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(24000)
        output.writeframes(raw)
    assert normalize_audio(buf.getvalue(), "wav") == raw
    for invalid in [b"", b"x", b"\x00" * (24000 * 2 * 60 + 2)]:
        with pytest.raises(HTTPException):
            normalize_audio(invalid, "pcm")
