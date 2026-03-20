"""
Error Logging Service - Saves application errors to the ErrorLog table.
Called from exception handlers and catch blocks throughout the app.
"""

from typing import Optional
from app.services.database import get_db_connection


def log_error(
    error_type: str,
    error_message: str,
    user_id: Optional[int] = None,
    endpoint: Optional[str] = None,
    request_body: Optional[str] = None,
    stack_trace: Optional[str] = None,
):
    """Log an error to the ErrorLog table. Silently fails if DB is down."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO ErrorLog (user_id, error_type, error_message, endpoint, request_body, stack_trace)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, error_type, error_message, endpoint, request_body, stack_trace))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception:
        pass  # Never let error logging crash the app
