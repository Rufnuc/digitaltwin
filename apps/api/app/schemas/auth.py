from __future__ import annotations

from pydantic import BaseModel, EmailStr

from app.schemas.common import ORMModel


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    role: str = "VIEWER"


class UserUpdate(BaseModel):
    full_name: str | None = None
    role: str | None = None
    is_active: bool | None = None
    password: str | None = None


class UserOut(ORMModel):
    id: int
    email: EmailStr
    full_name: str
    role: str
    is_active: bool
