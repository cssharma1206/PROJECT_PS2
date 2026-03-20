"""
Auth Middleware - JWT token validation for protected endpoints.
This is what makes JWT useful in Phase 2 (unlike Phase 1 where it was pointless).
Every API call passes through this to verify the Bearer token.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt

from app.config import JWT_SECRET_KEY, JWT_ALGORITHM

# This tells FastAPI to look for "Authorization: Bearer <token>" header
security_scheme = HTTPBearer()


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security_scheme)) -> dict:
    """
    Dependency that extracts and validates JWT from the Authorization header.
    Use in any endpoint that needs authentication:

        @router.get("/protected")
        def protected_route(user: dict = Depends(get_current_user)):
            return {"hello": user["username"]}
    """
    token = credentials.credentials

    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please login again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token. Please login again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check token type
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type. Access token required.",
        )

    return payload


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Dependency that requires the user to have Admin role."""
    if user.get("role") != "Admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required for this endpoint.",
        )
    return user
