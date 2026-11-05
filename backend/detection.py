"""API đăng ký người dùng và nhận lệnh phát từ hệ thống nhận diện."""
from __future__ import annotations

import re
import secrets
import time
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Path, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .config import DEVICE_ID_PATTERN, MAX_TEXT_LENGTH, MAX_USER_ID

DEVICE_ID = DEVICE_ID_PATTERN
UserIdPath = Annotated[int, Path(ge=1, le=MAX_USER_ID, description="ID người dùng đã đăng ký", examples=[1])]


class UserDetails(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [
        {"name": "Anh Quý", "text_to_speech": "Xin chào anh Quý", "device_id": "0001"}]})
    name: str = Field(default="", max_length=160)
    text_to_speech: str = Field(min_length=1, max_length=MAX_TEXT_LENGTH)
    device_id: str = Field(pattern=DEVICE_ID, examples=["0001"])

    @field_validator("text_to_speech")
    @classmethod
    def nonblank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Nội dung phát không được để trống")
        return value


class UserRegistration(UserDetails):
    model_config = ConfigDict(json_schema_extra={"examples": [
        {"user_id": 1, "name": "Anh Quý", "text_to_speech": "Xin chào anh Quý", "device_id": "0001"}]})
    user_id: int = Field(ge=1, le=MAX_USER_ID, strict=True)


class DeviceAlias(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device_id: str = Field(pattern=DEVICE_ID, examples=["speaker-01"])


class DetectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{"user_id": 1}]})
    user_id: int = Field(ge=1, le=MAX_USER_ID, strict=True)


class RegisteredUser(BaseModel):
    user_id: int = Field(ge=1, le=MAX_USER_ID, examples=[1])
    name: str
    text_to_speech: str
    device_id: str
    updated: float


class UsersResult(BaseModel):
    users: list[RegisteredUser]


class AliasResult(DeviceAlias):
    alias: str = Field(pattern=DEVICE_ID, examples=["0001"])


class AliasesResult(BaseModel):
    device_aliases: list[AliasResult]


class DetectResult(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "id": "0123456789abcdef0123456789abcdef", "status": "queued", "user_id": 1,
        "device_id": "speaker-01", "text_to_speech": "Xin chào anh Quý"}]})
    id: str = Field(description="Mã lượt phát do backend tạo; dùng GET /v1/jobs/{job_id} để theo dõi")
    status: Literal["queued"]
    user_id: int = Field(ge=1, le=MAX_USER_ID, examples=[1])
    device_id: str
    text_to_speech: str


def register_detection(app, *, operator_auth, connect, lock, device_keys, enqueue_speech):
    with connect() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY, name TEXT NOT NULL, text_to_speech TEXT NOT NULL,
                device_id TEXT NOT NULL, updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS device_aliases (
                alias TEXT PRIMARY KEY, device_id TEXT NOT NULL);
        """)

    def resolve_device(con, requested):
        alias = con.execute("SELECT device_id FROM device_aliases WHERE alias=?", (requested,)).fetchone()
        target = alias[0] if alias else requested
        if target not in device_keys:
            raise HTTPException(404, "Unknown device")
        return target

    def get_user(con, user_id):
        user = con.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not user:
            raise HTTPException(404, "Chưa đăng ký user_id. Gọi POST /v1/users trước.")
        return dict(user)

    @app.get("/v1/users", dependencies=[Depends(operator_auth)], tags=["Người dùng"],
             summary="Xem database người dùng", response_model=UsersResult)
    def list_users():
        with lock, connect() as con:
            return {"users": [dict(row) for row in con.execute("SELECT * FROM users ORDER BY user_id")]}

    @app.get("/v1/users/{user_id}", dependencies=[Depends(operator_auth)], tags=["Người dùng"],
             summary="Xem thông tin một người dùng", response_model=RegisteredUser)
    def read_user(user_id: UserIdPath):
        with lock, connect() as con:
            return get_user(con, user_id)

    @app.post("/v1/users", status_code=201, dependencies=[Depends(operator_auth)], tags=["Người dùng"],
              summary="Đăng ký người dùng và câu chào", response_model=RegisteredUser,
              description="Lưu user_id, nội dung và loa vào database. Thao tác này chưa phát audio.",
              responses={409: {"description": "user_id đã tồn tại"}, 404: {"description": "Chưa đăng ký hoặc ánh xạ loa"}})
    def register_user(request: UserRegistration):
        with lock, connect() as con:
            if con.execute("SELECT 1 FROM users WHERE user_id=?", (request.user_id,)).fetchone():
                raise HTTPException(409, "user_id đã được đăng ký. Dùng PUT /v1/users/{user_id} để cập nhật.")
            target = resolve_device(con, request.device_id)
            con.execute("INSERT INTO users VALUES (?,?,?,?,?)",
                        (request.user_id, request.name.strip(), request.text_to_speech, target, time.time()))
            return get_user(con, request.user_id)

    @app.put("/v1/users/{user_id}", dependencies=[Depends(operator_auth)], tags=["Người dùng"],
             summary="Cập nhật tên, nội dung hoặc loa", response_model=RegisteredUser)
    def update_user(user_id: UserIdPath, request: UserDetails):
        with lock, connect() as con:
            get_user(con, user_id)
            target = resolve_device(con, request.device_id)
            con.execute("UPDATE users SET name=?,text_to_speech=?,device_id=?,updated=? WHERE user_id=?",
                        (request.name.strip(), request.text_to_speech, target, time.time(), user_id))
            return get_user(con, user_id)

    @app.delete("/v1/users/{user_id}", status_code=204, dependencies=[Depends(operator_auth)],
                tags=["Người dùng"], summary="Xóa một người dùng")
    def delete_user(user_id: UserIdPath):
        with lock, connect() as con:
            if not con.execute("DELETE FROM users WHERE user_id=?", (user_id,)).rowcount:
                raise HTTPException(404, "Không tìm thấy user_id")
        return Response(status_code=204)

    @app.get("/v1/device-aliases", dependencies=[Depends(operator_auth)], tags=["Mã loa"],
             summary="Xem ánh xạ mã loa", response_model=AliasesResult)
    def list_aliases():
        with lock, connect() as con:
            return {"device_aliases": [dict(row) for row in con.execute("SELECT * FROM device_aliases ORDER BY alias")]}

    @app.put("/v1/device-aliases/{alias}", dependencies=[Depends(operator_auth)], tags=["Mã loa"],
             summary="Ánh xạ mã bên ngoài tới loa", response_model=AliasResult)
    def save_alias(alias: str, request: DeviceAlias):
        if not re.fullmatch(DEVICE_ID, alias):
            raise HTTPException(422, "Mã loa chỉ dùng chữ, số, dấu gạch ngang hoặc gạch dưới, tối đa 64 ký tự")
        with lock, connect() as con:
            if request.device_id not in device_keys:
                raise HTTPException(404, "Unknown device")
            if alias in device_keys and alias != request.device_id:
                raise HTTPException(409, "Mã này đã là ID của một loa khác")
            con.execute("INSERT INTO device_aliases VALUES (?,?) ON CONFLICT(alias) DO UPDATE SET device_id=excluded.device_id",
                        (alias, request.device_id))
            return {"alias": alias, "device_id": request.device_id}

    @app.delete("/v1/device-aliases/{alias}", status_code=204, dependencies=[Depends(operator_auth)],
                tags=["Mã loa"], summary="Xóa một ánh xạ mã loa")
    def delete_alias(alias: str):
        with lock, connect() as con:
            if not con.execute("DELETE FROM device_aliases WHERE alias=?", (alias,)).rowcount:
                raise HTTPException(404, "Không tìm thấy mã loa")
        return Response(status_code=204)

    @app.post("/v1/detect", status_code=202, dependencies=[Depends(operator_auth)], tags=["Phát âm thanh"],
              summary="Phát câu chào theo user_id", response_model=DetectResult,
              responses={404: {"description": "user_id chưa đăng ký"}, 429: {"description": "Hàng đợi đầy hoặc chạm giới hạn yêu cầu"},
                         502: {"description": "Không tạo hoặc tải được audio từ API TTS"}, 503: {"description": "TTS chưa được cấu hình"}})
    def detect(request: DetectRequest, response: Response):
        """Gửi user_id đã đăng ký; nội dung và loa được lấy hoàn toàn từ database."""
        with lock:
            with connect() as con:
                user = get_user(con, request.user_id)
                target = resolve_device(con, user["device_id"])
            text = user["text_to_speech"]
            event_key = secrets.token_hex(24)
            queued = enqueue_speech({"device_id": target, "text": text}, response,
                                    f"detect:{request.user_id}:{event_key}")
            return {"id": queued["id"], "status": queued["status"], "user_id": request.user_id,
                    "device_id": target, "text_to_speech": text}
