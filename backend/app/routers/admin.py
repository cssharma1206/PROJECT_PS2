"""
Admin Router - API endpoints for administration.
  GET /api/v1/admin/users       - List all users (Admin only)
  GET /api/v1/admin/logs/queries - Query execution logs (Admin only)
  GET /api/v1/admin/logs/errors  - Application error logs (Admin only)
"""

from fastapi import APIRouter, Depends, Query
from app.middleware.auth_middleware import require_admin
from app.services.database import get_db_connection
from app.services.error_logger import log_error
from app.models.dashboard import (
    UserListResponse, UserListItem,
    QueryHistoryResponse, QueryHistoryItem,
    ErrorLogResponse, ErrorLogItem,
)

router = APIRouter(prefix="/admin", tags=["Admin"])


# ═══════════════════════════════════════════════════════════════
# GET /admin/users - List All Users
# ═══════════════════════════════════════════════════════════════

@router.get("/users", response_model=UserListResponse)
def list_users(admin: dict = Depends(require_admin)):
    """List all registered users with their roles. Admin only."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.user_id, u.username, u.email, u.full_name,
                   r.role_name, u.is_active,
                   FORMAT(u.last_login, 'yyyy-MM-dd HH:mm:ss') AS last_login
            FROM Users_v2 u
            JOIN Roles r ON u.role_id = r.role_id
            ORDER BY u.user_id
        """)
        rows = cursor.fetchall()

        # Get total count
        cursor.execute("SELECT COUNT(*) FROM Users_v2")
        total = cursor.fetchone()[0]
        cursor.close()

        users = [
            UserListItem(
                user_id=r[0], username=r[1], email=r[2], full_name=r[3],
                role_name=r[4], is_active=bool(r[5]), last_login=r[6],
            )
            for r in rows
        ]
        return UserListResponse(users=users, total=total)

    except Exception as e:
        log_error("ADMIN_USERS", str(e), admin.get("user_id"), "/admin/users")
        return UserListResponse(users=[], total=0)
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
# GET /admin/logs/queries - Query Execution History
# ═══════════════════════════════════════════════════════════════

@router.get("/logs/queries", response_model=QueryHistoryResponse)
def get_query_logs(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    admin: dict = Depends(require_admin),
):
    """View all query execution logs. Shows what users asked and what SQL was generated. Admin only."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        offset = (page - 1) * limit

        cursor.execute(f"""
            SELECT log_id, query_text, generated_sql, method,
                   result_count, was_successful,
                   FORMAT(created_at, 'yyyy-MM-dd HH:mm:ss') AS created_at
            FROM QueryLog
            ORDER BY created_at DESC
            OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY
        """)
        rows = cursor.fetchall()

        cursor.execute("SELECT COUNT(*) FROM QueryLog")
        total = cursor.fetchone()[0]
        cursor.close()

        queries = [
            QueryHistoryItem(
                log_id=r[0], query_text=r[1], generated_sql=r[2],
                method=r[3], result_count=r[4],
                was_successful=bool(r[5]), created_at=r[6] or "",
            )
            for r in rows
        ]
        return QueryHistoryResponse(queries=queries, total=total, page=page, limit=limit)

    except Exception as e:
        log_error("ADMIN_QUERY_LOGS", str(e), admin.get("user_id"), "/admin/logs/queries")
        return QueryHistoryResponse(queries=[], total=0, page=page, limit=limit)
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
# GET /admin/logs/errors - Error Logs
# ═══════════════════════════════════════════════════════════════

@router.get("/logs/errors", response_model=ErrorLogResponse)
def get_error_logs(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    admin: dict = Depends(require_admin),
):
    """View application error logs. Shows what went wrong and where. Admin only."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        offset = (page - 1) * limit

        cursor.execute(f"""
            SELECT error_id, error_type, error_message, endpoint,
                   FORMAT(created_at, 'yyyy-MM-dd HH:mm:ss') AS created_at
            FROM ErrorLog
            ORDER BY created_at DESC
            OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY
        """)
        rows = cursor.fetchall()

        cursor.execute("SELECT COUNT(*) FROM ErrorLog")
        total = cursor.fetchone()[0]
        cursor.close()

        errors = [
            ErrorLogItem(
                error_id=r[0], error_type=r[1], error_message=r[2],
                endpoint=r[3], created_at=r[4] or "",
            )
            for r in rows
        ]
        return ErrorLogResponse(errors=errors, total=total)

    except Exception as e:
        log_error("ADMIN_ERROR_LOGS", str(e), admin.get("user_id"), "/admin/logs/errors")
        return ErrorLogResponse(errors=[], total=0)
    finally:
        conn.close()
