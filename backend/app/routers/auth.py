"""
Auth Router - API endpoints for authentication.
  POST /api/v1/auth/login     - Login and get tokens
  POST /api/v1/auth/register  - Register new user (Admin only)
  POST /api/v1/auth/refresh   - Get new access token using refresh token
  POST /api/v1/auth/logout    - Revoke all tokens
  GET  /api/v1/auth/me        - Get current user profile
"""

from fastapi import APIRouter, HTTPException, Depends, Request, status
import traceback

from app.models.auth import (
    LoginRequest, LoginResponse, RegisterRequest, RegisterResponse,
    RefreshTokenRequest, RefreshTokenResponse, UserResponse, MessageResponse,
)
from app.services.auth_service import (
    authenticate_user, register_user,
    create_access_token, create_refresh_token,
    store_refresh_token, validate_refresh_token,
    revoke_user_tokens, get_user_by_id, decode_token,
)
from app.middleware.auth_middleware import get_current_user, require_admin
from app.services.error_logger import log_error
from app.config import ACCESS_TOKEN_EXPIRE_MINUTES

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ─── POST /login ──────────────────────────────────────────────
@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request):
    """Authenticate user and return access + refresh tokens."""
    user, error = authenticate_user(body.username, body.password)

    if error:
        log_error("AUTH_FAILED", error, endpoint="/auth/login", request_body=body.username)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=error)

    # Create tokens
    access_token = create_access_token(
        user["user_id"], user["username"],
        user["role_name"], user["application_id"]
    )
    refresh_token = create_refresh_token(user["user_id"])

    # Store refresh token in DB
    client_ip = request.client.host if request.client else None
    store_refresh_token(user["user_id"], refresh_token, client_ip)

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserResponse(**user),
    )


# ─── POST /register ──────────────────────────────────────────
@router.post("/register", response_model=RegisterResponse)
def register(body: RegisterRequest, admin: dict = Depends(require_admin)):
    """Register a new user. Admin only."""
    user_id, error = register_user(
        body.username, body.password, body.email, body.full_name, body.role_id
    )

    if error:
        log_error("REGISTRATION_FAILED", error, user_id=admin.get("user_id"), endpoint="/auth/register")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)

    return RegisterResponse(user_id=user_id, username=body.username)


# ─── POST /refresh ────────────────────────────────────────────
@router.post("/refresh", response_model=RefreshTokenResponse)
def refresh_token(body: RefreshTokenRequest):
    """Get a new access token using a valid refresh token."""
    try:
        # First decode the JWT to check it's structurally valid
        payload = decode_token(body.refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    # Then check it exists in DB and is not revoked
    user_id = validate_refresh_token(body.refresh_token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Refresh token revoked or expired")

    # Get user details for new access token
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    access_token = create_access_token(
        user["user_id"], user["username"],
        user["role_name"], user["application_id"]
    )

    return RefreshTokenResponse(
        access_token=access_token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# ─── POST /logout ─────────────────────────────────────────────
@router.post("/logout", response_model=MessageResponse)
def logout(user: dict = Depends(get_current_user)):
    """Revoke all refresh tokens for the current user."""
    revoke_user_tokens(user["user_id"])
    return MessageResponse(message="Logged out successfully. All tokens revoked.")


# ─── GET /me ──────────────────────────────────────────────────
@router.get("/me", response_model=UserResponse)
def get_me(user: dict = Depends(get_current_user)):
    """Get the current authenticated user's profile."""
    user_data = get_user_by_id(user["user_id"])
    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(**user_data)
