"""
Access Control Helper - ApplicationAccessMaster-based authorization.

Used by query routers to build a SQL WHERE-filter that restricts a user's
view to only the applications they're allowed to see.

Rules:
  - Admin role + ZERO rows in ApplicationAccessMaster → no filter (sees all)
  - Any rows in ApplicationAccessMaster → filter by those ApplicationIds
  - No role=Admin AND no rows → fail-safe, sees nothing (misconfigured user)

ApplicationAccessMaster stores AppCode (APP001, APP002).
We resolve those to ApplicationMaster.AppId (1, 2) since CommunicationMaster
stores ApplicationId (int), not AppCode (string).
"""

from typing import List, Tuple
from app.services.database import get_db_connection
from app.services.error_logger import log_error


def get_allowed_app_ids(user_id: int) -> List[int]:
    """
    Look up which ApplicationIds a user is allowed to query.
    Returns [] if user has no rows in ApplicationAccessMaster.
    """
    if not user_id:
        return []

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT am.AppId
            FROM ApplicationAccessMaster aam
            INNER JOIN ApplicationMaster am
                ON aam.AppCode = am.ApplicationCode
            WHERE aam.UserID = ?
            """,
            (user_id,),
        )
        rows = cursor.fetchall()
        cursor.close()
        return [r[0] for r in rows]
    except Exception as e:
        log_error("ACCESS_CONTROL", str(e), user_id=user_id, endpoint="get_allowed_app_ids")
        return []
    finally:
        conn.close()


def build_app_filter(user: dict, column: str = "ApplicationId") -> Tuple[str, str]:
    """
    Build a WHERE-compatible SQL fragment for the user's app access.

    Args:
        user: The JWT user dict (must have user_id and role)
        column: The column name to filter on. Default 'ApplicationId'
                for CommunicationMaster. Use 'AppId' for
                CommunicationErrorMaster, 'ApplicationCode' for
                ApplicationAccessMaster, etc.

    Returns:
        (filter_sql, scope_label)
        filter_sql  - "" (no filter, admin), "ApplicationId IN (1,2)", or "1=0" (blocked)
        scope_label - 'admin', 'scoped', or 'blocked' - useful for logging/debug

    Rules:
        Admin role + 0 access rows           → "" (full access)
        Has access rows                       → "col IN (id1, id2, ...)"
        Non-admin + 0 access rows             → "1=0" (fail-safe, sees nothing)
    """
    user_id = user.get("user_id")
    role = user.get("role", "")
    allowed_ids = get_allowed_app_ids(user_id)

    if role == "Admin" and len(allowed_ids) == 0:
        return "", "admin"

    if len(allowed_ids) > 0:
        id_list = ",".join(str(i) for i in allowed_ids)
        return f"{column} IN ({id_list})", "scoped"

    # Non-admin with no access rows = misconfigured, fail safe
    return "1=0", "blocked"