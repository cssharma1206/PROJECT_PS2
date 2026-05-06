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

import re

# Tables that have an app-access column, with the column name per table
ACCESS_RELEVANT_TABLES = {
    "CommunicationMaster": "ApplicationId",
    "CommunicationErrorMaster": "AppId",
    "ApplicationMaster": "AppId",
}


def inject_access_into_sql(sql: str, user: dict) -> tuple:
    """
    Inject an access filter into generated SQL for category mode.

    Returns (modified_sql, error_or_none).
    - If user is admin with full access: returns (sql, None) unchanged
    - If SQL references an access-relevant table: injects filter, returns (modified_sql, None)
    - If SQL cannot be safely filtered: returns (None, error_message) — fail-closed

    Strategy: find the first access-relevant table in the FROM/JOIN clauses,
    extract its alias, and inject <alias>.<col> IN (...) into the WHERE clause.
    """
    allowed_ids = get_allowed_app_ids(user.get("user_id"))

    # Admin or full-access → no-op
    if not allowed_ids and user.get("role") == "Admin":
        return sql, None

    # Non-admin with no access → fail-closed (shouldn't happen, but belt + suspenders)
    if not allowed_ids:
        return None, "User has no application access."

    # Build the IN clause
    ids_list = ",".join(str(x) for x in allowed_ids)

    # Find first access-relevant table in FROM or JOIN clause, get its alias
    # Match both "FROM TableName alias" and "JOIN TableName alias"
    found_table = None
    found_alias = None

    # SQL keywords that can appear after a table name but are NOT aliases.
    # Without this guard, "FROM CommunicationMaster GROUP BY ..." would
    # incorrectly capture "GROUP" as the table's alias, producing invalid
    # SQL like "GROUP.ApplicationId IN (1)".
    SQL_KEYWORDS_AFTER_TABLE = (
        r"WHERE|GROUP|ORDER|HAVING|LIMIT|UNION|INNER|LEFT|RIGHT|"
        r"FULL|CROSS|JOIN|ON|AS"
    )
 
    for table, col in ACCESS_RELEVANT_TABLES.items():
        # Pattern 1: real alias — table followed by a word that is NOT a SQL keyword.
        # Uses (?!keyword\b) negative lookahead to skip keywords.
        pattern = (
            rf"\b(?:FROM|JOIN)\s+{re.escape(table)}\s+"
            rf"(?!(?:{SQL_KEYWORDS_AFTER_TABLE})\b)"
            rf"(\w+)"
        )
        m = re.search(pattern, sql, re.IGNORECASE)
        if m:
            found_table = table
            found_alias = m.group(1)
            break
        # Pattern 2: no alias — table followed by end-of-string OR a SQL keyword.
        # This branch handles "FROM CommunicationMaster GROUP BY ..."
        # by NOT capturing GROUP, then prefixing columns with the full table name.
        pattern_noalias = rf"\b(?:FROM|JOIN)\s+{re.escape(table)}\b"
        m2 = re.search(pattern_noalias, sql, re.IGNORECASE)
        if m2:
            found_table = table
            found_alias = table  # use full table name as the qualifier
            break

    if not found_table:
        return None, (
            "Access filter could not be applied: no access-controlled table "
            "found in query. Query rejected for safety."
        )

    col = ACCESS_RELEVANT_TABLES[found_table]
    filter_clause = f"{found_alias}.{col} IN ({ids_list})"

    # Inject into WHERE clause
    # Case 1: has WHERE already — append AND before GROUP BY / ORDER BY / end
    # Case 2: no WHERE — insert WHERE before GROUP BY / ORDER BY / end
    has_where = re.search(r"\bWHERE\b", sql, re.IGNORECASE)

    if has_where:
        # Find end of WHERE clause: before GROUP BY, ORDER BY, HAVING, or end
        # Split at the first occurrence of any of these keywords
        split_match = re.search(
            r"\b(GROUP\s+BY|ORDER\s+BY|HAVING)\b",
            sql, re.IGNORECASE
        )
        if split_match:
            before = sql[:split_match.start()].rstrip()
            after = sql[split_match.start():]
            modified_sql = f"{before} AND {filter_clause} {after}"
        else:
            modified_sql = f"{sql.rstrip().rstrip(';')} AND {filter_clause}"
    else:
        # No WHERE — insert WHERE before GROUP BY / ORDER BY, or at end
        split_match = re.search(
            r"\b(GROUP\s+BY|ORDER\s+BY|HAVING)\b",
            sql, re.IGNORECASE
        )
        if split_match:
            before = sql[:split_match.start()].rstrip()
            after = sql[split_match.start():]
            modified_sql = f"{before} WHERE {filter_clause} {after}"
        else:
            modified_sql = f"{sql.rstrip().rstrip(';')} WHERE {filter_clause}"

    return modified_sql, None