from fastapi.testclient import TestClient
import pytest

from backend.app import create_app

OP = {"Authorization": "Bearer detection-operator-test-key"}
DEV = {"Authorization": "Bearer detection-device-test-key"}
DEVICES = {"speaker-01": "detection-device-test-key", "speaker-02": "second-device-test-key"}
PROFILE = {"user_id": 1, "name": "Anh Quý", "text_to_speech": "Xin chào anh Quý", "device_id": "speaker-01"}
DETAILS = {key: value for key, value in PROFILE.items() if key != "user_id"}


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(tmp_path, "detection-operator-test-key", DEVICES.copy(), "tone"))


def register(client, **changes):
    response = client.post("/v1/users", headers=OP, json={**PROFILE, **changes})
    assert response.status_code == 201, response.text
    return response.json()


def test_registration_is_explicit_and_does_not_play(client):
    assert client.post("/v1/detect", headers=OP, json={"user_id": 1}).status_code == 404
    assert client.get("/v1/users", headers=OP).json()["users"] == []
    user = register(client)
    assert user["name"] == PROFILE["name"]
    assert client.post("/v1/users", headers=OP, json=PROFILE).status_code == 409
    assert client.get("/v1/dashboard/overview", headers=OP).json()["jobs"] == []


def test_detection_user_to_real_device_queue(client):
    assert client.put("/v1/device-aliases/0001", headers=OP, json={"device_id": "speaker-01"}).status_code == 200
    register(client, device_id="0001")
    detected = client.post("/v1/detect", headers=OP,
                           json={"user_id": 1})
    assert detected.status_code == 202
    data = detected.json()
    assert data["device_id"] == "speaker-01"
    assert data["status"] == "queued" and data["text_to_speech"] == PROFILE["text_to_speech"]
    job = client.get("/v1/devices/speaker-01/next", headers=DEV).json()
    assert job["id"] == data["id"]
    audio = client.get(f"/v1/devices/speaker-01/audio/{job['id']}", headers=DEV,
                       params={"lease": job["lease"]})
    assert audio.status_code == 200 and len(audio.content) == job["audio_bytes"] == 48000
    assert client.post("/v1/devices/speaker-01/ack", headers=DEV,
                       json={"id": job["id"], "lease": job["lease"], "status": "played"}).status_code == 200


def test_every_call_plays_without_cooldown(client):
    register(client)
    ids = []
    for _ in range(3):
        result = client.post("/v1/detect", headers=OP, json={"user_id": 1})
        assert result.status_code == 202
        assert set(result.json()) == {"id", "status", "user_id", "device_id", "text_to_speech"}
        ids.append(result.json()["id"])
    assert len(set(ids)) == 3
    assert len(client.get("/v1/dashboard/overview", headers=OP).json()["jobs"]) == 3


@pytest.mark.parametrize("extra", [{"device_id": "speaker-02"}, {"text_to_speech": "Câu khác"}, {"detect_person": False}])
def test_detect_rejects_request_overrides(client, extra):
    register(client)
    assert client.post("/v1/detect", headers=OP, json={"user_id": 1, **extra}).status_code == 422
    assert client.get("/v1/dashboard/overview", headers=OP).json()["jobs"] == []


def test_detect_reads_current_database_text_and_device(client):
    register(client)
    first = client.post("/v1/detect", headers=OP, json={"user_id": 1})
    assert first.json()["text_to_speech"] == PROFILE["text_to_speech"]
    assert first.json()["device_id"] == "speaker-01"
    updated = client.put("/v1/users/1", headers=OP,
                         json={**DETAILS, "text_to_speech": "Nội dung mới trong database", "device_id": "speaker-02"})
    assert updated.status_code == 200
    next_call = client.post("/v1/detect", headers=OP, json={"user_id": 1})
    assert next_call.status_code == 202
    assert next_call.json()["text_to_speech"] == "Nội dung mới trong database"
    assert next_call.json()["device_id"] == "speaker-02"


def test_openapi_detect_only_documents_user_id(client):
    schema = client.get("/openapi.json").json()
    operation = schema["paths"]["/v1/detect"]["post"]
    assert operation.get("parameters", []) == []
    assert operation["security"]
    request = schema["components"]["schemas"]["DetectRequest"]
    assert set(request["properties"]) == {"user_id"}
    assert request["required"] == ["user_id"]
    assert request["examples"] == [{"user_id": 1}]


def test_users_and_aliases_persist_after_restart(client, tmp_path):
    register(client)
    client.put("/v1/device-aliases/0001", headers=OP, json={"device_id": "speaker-01"})
    restarted = TestClient(create_app(tmp_path, "detection-operator-test-key", DEVICES.copy(), "tone"))
    data = restarted.get("/v1/users", headers=OP).json()
    assert data["users"][0]["text_to_speech"] == PROFILE["text_to_speech"]
    assert restarted.get("/v1/device-aliases", headers=OP).json()["device_aliases"] == [{"alias": "0001", "device_id": "speaker-01"}]
    assert restarted.post("/v1/detect", headers=OP, json={"user_id": 1}).status_code == 202


def test_users_auth_validation_and_update_delete(client):
    for headers in [{}, DEV]:
        assert client.get("/v1/users", headers=headers).status_code == 401
        assert client.post("/v1/users", headers=headers, json=PROFILE).status_code == 401
        assert client.post("/v1/detect", headers=headers, json={"user_id": 1}).status_code == 401
        assert client.put("/v1/device-aliases/0001", headers=headers, json={"device_id": "speaker-01"}).status_code == 401
    for changes in [{"user_id": True}, {"user_id": 0}, {"text_to_speech": " "}, {"text_to_speech": "x" * 1001}]:
        assert client.post("/v1/users", headers=OP, json={**PROFILE, **changes}).status_code == 422
    assert client.post("/v1/users", headers=OP, json={**PROFILE, "device_id": "missing"}).status_code == 404
    assert client.post("/v1/detect", headers=OP, json={"user_id": 1, "typo": 1}).status_code == 422
    assert client.put("/v1/users/1", headers=OP, json=DETAILS).status_code == 404
    register(client)
    updated = client.put("/v1/users/1", headers=OP, json={**DETAILS, "text_to_speech": "Chào lại"})
    assert updated.status_code == 200 and updated.json()["text_to_speech"] == "Chào lại"
    assert client.get("/v1/users/1", headers=OP).json()["text_to_speech"] == "Chào lại"
    assert client.put("/v1/device-aliases/speaker-01", headers=OP, json={"device_id": "speaker-02"}).status_code == 409
    assert client.put("/v1/device-aliases/bad%20alias", headers=OP, json={"device_id": "speaker-01"}).status_code == 422
    assert client.put("/v1/device-aliases/0001", headers=OP, json={"device_id": "speaker-01"}).status_code == 200
    assert client.delete("/v1/device-aliases/0001", headers=OP).status_code == 204
    assert client.delete("/v1/users/1", headers=OP).status_code == 204
    assert client.post("/v1/detect", headers=OP, json={"user_id": 1}).status_code == 404
