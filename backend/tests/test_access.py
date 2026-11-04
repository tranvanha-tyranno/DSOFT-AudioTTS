import json

import pytest

from backend.access import access_info


def test_access_from_persistent_volume(tmp_path, monkeypatch):
    monkeypatch.delenv("SPEAKER_API_KEY", raising=False)
    monkeypatch.setenv("SPEAKER_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SPEAKER_PUBLIC_URL", "http://192.168.1.50:8090")
    (tmp_path / "demo_access.json").write_text(json.dumps({"operator_key": "operator-key-from-volume"}))
    info = access_info()
    assert info["dashboard_url"] == "http://192.168.1.50:8090/"
    assert info["operator_key"] == "operator-key-from-volume"
    assert info["login_url"].endswith("/#key=operator-key-from-volume")


def test_explicit_environment_key_and_proxy_url(monkeypatch):
    monkeypatch.setenv("SPEAKER_API_KEY", "operator-key-from-env")
    info = access_info("https://speaker.example.test/")
    assert info["login_url"] == "https://speaker.example.test/#key=operator-key-from-env"


def test_missing_access_is_explicit(tmp_path, monkeypatch):
    monkeypatch.delenv("SPEAKER_API_KEY", raising=False)
    monkeypatch.setenv("SPEAKER_DATA_DIR", str(tmp_path))
    with pytest.raises(RuntimeError, match="Khởi động backend"):
        access_info()
