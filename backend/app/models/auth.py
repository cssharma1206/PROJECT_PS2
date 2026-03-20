"""
Auth Models - Pydantic schemas for authentication endpoints.
These define exactly what data goes in and comes out of each API.
"""

from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime


# ─── REQUEST MODELS ───────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100, examples=["admin"])
    password: str = Field(..., min_length=1, max_length=100, examples=["admin123"])


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=100, examples=["newuser"])
    password: str = Field(..., min_length=6, max_length=100, examples=["password123"])
    email: str = Field(..., max_length=200, examples=["user@anandrathi.com"])
    full_name: str = Field(..., min_length=1, max_length=200, examples=["Parv Sharma"])
    role_id: int = Field(..., ge=1, examples=[3])


class RefreshTokenRequest(BaseModel):
    refresh_token: str


# ─── RESPONSE MODELS ──────────────────────────────────────────

class UserResponse(BaseModel):
    user_id: int
    username: str
    email: str
    full_name: str
    role_id: int
    role_name: str
    is_active: bool
    can_query: bool
    can_export: bool
    can_admin: bool
    application_id: Optional[int] = None
    app_code: Optional[str] = None


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class RefreshTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class RegisterResponse(BaseModel):
    user_id: int
    username: str
    message: str = "User registered successfully"


class MessageResponse(BaseModel):
    message: str
