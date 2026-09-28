from __future__ import annotations

from pydantic import BaseModel, EmailStr

from app.schemas.common import ORMModel


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    # Device binding: a browser-generated id + a friendly label (user agent), used
    # to gate sign-in for device-locked accounts / the SALESGIRL role.
    device_id: str | None = None
    device_label: str | None = None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    role: str = "STAFF"


class UserUpdate(BaseModel):
    full_name: str | None = None
    email: EmailStr | None = None
    role: str | None = None
    is_active: bool | None = None
    password: str | None = None
    device_locked: bool | None = None


class UserOut(ORMModel):
    id: int
    email: EmailStr
    full_name: str
    role: str
    is_active: bool
    device_locked: bool = False
