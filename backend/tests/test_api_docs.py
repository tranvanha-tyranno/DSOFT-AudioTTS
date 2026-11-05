from fastapi.testclient import TestClient

from backend.app import create_app


def test_integration_docs_exclude_firmware_and_dashboard(tmp_path):
    client = TestClient(create_app(tmp_path, "documentation-operator-key", {"speaker-01": "documentation-device-key"}, "tone"))
    public = client.get("/openapi.json").json()
    internal = client.get("/openapi-internal.json").json()
    assert "/v1/detect" in public["paths"]
    assert "/v1/users" in public["paths"]
    assert "/v1/device-aliases" in public["paths"]
    assert "/v1/jobs/{job_id}" in public["paths"]
    assert "/v1/speak" not in public["paths"]
    assert not any(path.startswith("/v1/dashboard/") or path.startswith("/v1/devices/") for path in public["paths"])
    assert set(public["components"]["securitySchemes"]) == {"AdminKey"}
    assert set(internal["components"]["securitySchemes"]) == {"AdminKey", "DeviceToken"}
    assert "/v1/speak" in internal["paths"]
    assert "/v1/devices/{device_id}/next" in internal["paths"]
    assert "/v1/dashboard/tts" in internal["paths"]
    assert "/v1/detect" not in internal["paths"]
    assert client.get("/docs").status_code == 200
    assert client.get("/docs/internal").status_code == 200
    detect = public["paths"]["/v1/detect"]["post"]
    assert detect.get("parameters", []) == []
    assert detect["responses"]["202"]["content"]["application/json"]["schema"]["$ref"].endswith("/DetectResult")
    assert set(public["components"]["schemas"]["DetectResult"]["properties"]) == {"id", "status", "user_id", "device_id", "text_to_speech"}


def test_integration_and_internal_tokens_still_enforce_roles(tmp_path):
    client = TestClient(create_app(tmp_path, "documentation-operator-key", {"speaker-01": "documentation-device-key"}, "tone"))
    admin = {"Authorization": "Bearer documentation-operator-key"}
    device = {"Authorization": "Bearer documentation-device-key"}
    assert client.get("/v1/users", headers=device).status_code == 401
    assert client.get("/v1/device-aliases", headers=device).status_code == 401
    assert client.get("/v1/devices/speaker-01/next", headers=admin).status_code == 401
    assert client.get("/v1/devices/speaker-01/next", headers=device).status_code == 204
    assert client.get("/v1/dashboard/tts", headers=admin).status_code == 200
    assert client.post("/v1/detect", headers=admin, json={"user_id": 1}).status_code == 404
