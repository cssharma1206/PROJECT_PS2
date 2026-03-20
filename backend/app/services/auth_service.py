"""
Auth Service - Business logic for authentication and authorization.
Handles login, registration, JWT creation, token storage, and validation.
"""

import bcrypt
import jwt
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from app.config import (
    JWT_SECRET_KEY, JWT_ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS
)
from app.services.database import get_db_connection


# ═══════════════════════════════════════════════════════════════
# PASSWORD UTILITIES
# ═══════════════════════════════════════════════════════════════

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


# ═══════════════════════════════════════════════════════════════
# JWT TOKEN UTILITIES
# ═══════════════════════════════════════════════════════════════

def create_access_token(user_id: int, username: str, role_name: str, application_id: Optional[int]) -> str:
    payload = {
        "user_id": user_id,
        "username": username,
        "role": role_name,
        "application_id": application_id,
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: int) -> str:
    payload = {
        "user_id": user_id,
        "type": "refresh",
        "exp": datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token. Raises jwt exceptions on failure."""
    return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])


def hash_token_for_storage(token: str) -> str:
    """SHA-256 hash of token for safe storage in the Token table."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ═══════════════════════════════════════════════════════════════
# USER AUTHENTICATION
# ═══════════════════════════════════════════════════════════════

def authenticate_user(username: str, password: str) -> Tuple[Optional[dict], Optional[str]]:
    """
    Validate credentials against Users_v2 + Roles tables.
    Returns (user_dict, None) on success or (None, error_message) on failure.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.user_id, u.username, u.password_hash, u.email, u.full_name,
                   u.role_id, u.is_active,
                   r.role_name, r.can_query, r.can_export, r.can_admin,
                   r.application_id, r.app_code
            FROM Users_v2 u
            JOIN Roles r ON u.role_id = r.role_id
            WHERE u.username = ?
        """, (username,))

        row = cursor.fetchone()
        if not row:
            return None, "Invalid username or password"

        user_id, uname, pwd_hash, email, full_name, role_id, is_active, \
            role_name, can_query, can_export, can_admin, application_id, app_code = row

        if not is_active:
            return None, "Account is disabled. Contact your administrator."

        if not verify_password(password, pwd_hash):
            return None, "Invalid username or password"

        # Update last_login
        cursor.execute(
            "UPDATE Users_v2 SET last_login = GETDATE() WHERE user_id = ?",
            (user_id,)
        )
        conn.commit()
        cursor.close()

        return {
            "user_id": user_id,
            "username": uname,
            "email": email,
            "full_name": full_name,
            "role_id": role_id,
            "role_name": role_name,
            "is_active": bool(is_active),
            "can_query": bool(can_query),
            "can_export": bool(can_export),
            "can_admin": bool(can_admin),
            "application_id": application_id,
            "app_code": app_code,
        }, None

    except Exception as e:
        return None, f"Authentication error: {str(e)}"
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
# USER REGISTRATION
# ═══════════════════════════════════════════════════════════════

def register_user(username: str, password: str, email: str, full_name: str, role_id: int) -> Tuple[Optional[int], Optional[str]]:
    """
    Register a new user. Returns (user_id, None) on success or (None, error).
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Check if username already exists
        cursor.execute("SELECT COUNT(*) FROM Users_v2 WHERE username = ?", (username,))
        if cursor.fetchone()[0] > 0:
            return None, "Username already exists"

        # Check if email already exists
        cursor.execute("SELECT COUNT(*) FROM Users_v2 WHERE email = ?", (email,))
        if cursor.fetchone()[0] > 0:
            return None, "Email already registered"

        # Verify role exists
        cursor.execute("SELECT COUNT(*) FROM Roles WHERE role_id = ?", (role_id,))
        if cursor.fetchone()[0] == 0:
            return None, f"Role ID {role_id} does not exist"

        pwd_hash = hash_password(password)
        cursor.execute("""
            INSERT INTO Users_v2 (username, password_hash, email, full_name, role_id)
            OUTPUT INSERTED.user_id
            VALUES (?, ?, ?, ?, ?)
        """, (username, pwd_hash, email, full_name, role_id))

        new_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        return new_id, None

    except Exception as e:
        conn.rollback()
        return None, f"Registration error: {str(e)}"
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
# TOKEN STORAGE (Refresh tokens in DB)
# ═══════════════════════════════════════════════════════════════

def store_refresh_token(user_id: int, token: str, ip_address: str = None):
    """Save a hashed refresh token to the Token table."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        token_hash = hash_token_for_storage(token)
        expires_at = datetime.now() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        cursor.execute("""
            INSERT INTO Token (user_id, token_hash, token_type, expires_at, ip_address)
            VALUES (?, ?, 'refresh', ?, ?)
        """, (user_id, token_hash, expires_at, ip_address))
        conn.commit()
        cursor.close()
    finally:
        conn.close()


def validate_refresh_token(token: str) -> Optional[int]:
    """
    Check if a refresh token exists in DB and is not revoked/expired.
    Returns user_id if valid, None otherwise.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        token_hash = hash_token_for_storage(token)
        cursor.execute("""
            SELECT user_id FROM Token
            WHERE token_hash = ?
              AND is_revoked = 0
              AND expires_at > GETDATE()
              AND token_type = 'refresh'
        """, (token_hash,))
        row = cursor.fetchone()
        cursor.close()
        return row[0] if row else None
    finally:
        conn.close()


def revoke_user_tokens(user_id: int):
    """Revoke all refresh tokens for a user (used on logout)."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE Token SET is_revoked = 1 WHERE user_id = ? AND is_revoked = 0",
            (user_id,)
        )
        conn.commit()
        cursor.close()
    finally:
        conn.close()


def get_user_by_id(user_id: int) -> Optional[dict]:
    """Fetch user details by ID. Used for /me endpoint and token refresh."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.user_id, u.username, u.email, u.full_name,
                   u.role_id, u.is_active,
                   r.role_name, r.can_query, r.can_export, r.can_admin,
                   r.application_id, r.app_code
            FROM Users_v2 u
            JOIN Roles r ON u.role_id = r.role_id
            WHERE u.user_id = ?
        """, (user_id,))
        row = cursor.fetchone()
        cursor.close()
        if not row:
            return None
        return {
            "user_id": row[0], "username": row[1], "email": row[2],
            "full_name": row[3], "role_id": row[4], "is_active": bool(row[5]),
            "role_name": row[6], "can_query": bool(row[7]),
            "can_export": bool(row[8]), "can_admin": bool(row[9]),
            "application_id": row[10], "app_code": row[11],
        }
    finally:
        conn.close()
