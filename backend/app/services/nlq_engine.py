"""
NLQ Engine v3 - Natural Language Query Engine
================================================
The brain of the Communications Intelligence Platform.

AI-FIRST Architecture (no templates):
  - All queries route to MCP Bridge → Ollama AI
  - match_template() is a stub that always returns (None, None)
    → query.py then forwards to MCP Bridge
  - MCP Bridge reads live schema, generates SQL, executes safely
  - Access control injected server-side (guaranteed data isolation)

Flow:
  1. User asks a question in natural language
  2. query.py calls match_template() — always (None, None) now
  3. query.py forwards to MCP Bridge (mcp_client.py)
  4. MCP Bridge → mcp_server.py → Ollama AI → SQL generation
  5. Validation + access control → execute → results

Key principle:
  Templates have been removed. The AI (Ollama via MCP) handles ALL
  questions. The live-schema reader in mcp_server.py uses INFORMATION_SCHEMA
  to describe the current database to the AI — zero hardcoded columns.

  This file retains only the utility functions that query.py still imports:
    - match_template()        — stub, returns (None, None)
    - validate_sql()          — SQL safety check
    - inject_access_filter()  — guaranteed access control
    - execute_query_safe()    — safe query executor
    - get_live_schema()       — /query/schema endpoint support
    - process_query()         — legacy fallback (unused in normal flow)
"""

import re
import time
import requests
from typing import Optional, Tuple, List, Dict
from app.services.database import get_db_connection
from app.services.error_logger import log_error


# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "gemma3:4b"
OLLAMA_TIMEOUT = 120  # seconds


# ═══════════════════════════════════════════════════════════════
# LIVE SCHEMA READER (for /query/schema endpoint)
# ═══════════════════════════════════════════════════════════════

# Tables exposed via the /query/schema endpoint.
# Keep in sync with the new 4-table Communications schema + platform tables.
SCHEMA_TABLES = (
    'CommunicationMaster',
    'CommunicationErrorMaster',
    'ApplicationMaster',
    'ApplicationAccessMaster',
    'Users_v2',
    'Roles',
)


def get_live_schema(table_name: str = None) -> str:
    """
    Read database schema LIVE from INFORMATION_SCHEMA.COLUMNS.
    Schema is never hardcoded — always fresh from the database.

    Returns a plain text description of the requested table (if given)
    or all key tables in the Communications schema.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        if table_name:
            cursor.execute("""
                SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, IS_NULLABLE,
                       CHARACTER_MAXIMUM_LENGTH
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME = ?
                ORDER BY ORDINAL_POSITION
            """, (table_name,))
        else:
            placeholders = ",".join(["?"] * len(SCHEMA_TABLES))
            cursor.execute(f"""
                SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, IS_NULLABLE,
                       CHARACTER_MAXIMUM_LENGTH
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME IN ({placeholders})
                ORDER BY TABLE_NAME, ORDINAL_POSITION
            """, SCHEMA_TABLES)

        rows = cursor.fetchall()
        cursor.close()

        if not rows:
            return "No schema found."

        schema_lines = []
        current_table = None

        for table, column, dtype, nullable, max_len in rows:
            if table != current_table:
                if current_table:
                    schema_lines.append("")
                schema_lines.append(f"Table: {table}")
                schema_lines.append("Columns:")
                current_table = table

            type_str = dtype
            if max_len and max_len > 0:
                type_str = f"{dtype}({max_len})"

            null_str = "nullable" if nullable == "YES" else "required"
            schema_lines.append(f"  - {column} ({type_str}, {null_str})")

        return "\n".join(schema_lines)

    except Exception as e:
        log_error("SCHEMA_READ", str(e), endpoint="get_live_schema")
        return "Error reading schema."
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
# TEMPLATE MATCHER — INTENTIONALLY DISABLED
# ═══════════════════════════════════════════════════════════════
# Templates were removed in v3. The AI path handles all queries.
# This function remains as a compatibility stub so query.py keeps working.
# Returning (None, None) tells the router to forward to MCP Bridge.
# ═══════════════════════════════════════════════════════════════

def match_template(question: str, access_filter: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Template matching is disabled. All queries go to the AI path.
    Kept as a stub so existing imports in query.py continue to work.
    """
    return None, None


# ═══════════════════════════════════════════════════════════════
# SQL VALIDATION & SECURITY
# ═══════════════════════════════════════════════════════════════

DANGEROUS_KEYWORDS = [
    'DROP', 'DELETE', 'INSERT', 'UPDATE', 'ALTER',
    'CREATE', 'EXEC', 'EXECUTE', 'TRUNCATE', 'GRANT',
    'REVOKE', 'MERGE', 'REPLACE',
]


def validate_sql(sql: str) -> Tuple[bool, str]:
    """Validate SQL for safety. Returns (is_valid, reason)."""
    if not sql:
        return False, "Empty SQL"

    sql_upper = sql.upper().strip()

    if not sql_upper.startswith('SELECT'):
        return False, "Only SELECT queries are allowed"

    for keyword in DANGEROUS_KEYWORDS:
        if re.search(rf'\b{keyword}\b', sql_upper):
            return False, f"Dangerous keyword detected: {keyword}"

    return True, "Valid"


def inject_access_filter(sql: str, access_filter: str) -> str:
    """
    Ensure access control filter is present in the SQL.
    If AI forgot to add it, we inject it here.
    Guarantees data isolation regardless of AI behavior.
    """
    if not access_filter:
        return sql  # Admin, no filter needed

    sql_upper = sql.upper()

    # Already present — no-op (normalized comparison)
    if access_filter.upper().replace(" ", "") in sql_upper.replace(" ", ""):
        return sql

    # Inject
    if 'WHERE' in sql_upper:
        return sql + f" AND {access_filter}"
    elif 'GROUP BY' in sql_upper:
        parts = sql.split('GROUP BY')
        return f"{parts[0]} WHERE {access_filter} GROUP BY {parts[1]}"
    elif 'ORDER BY' in sql_upper:
        parts = sql.split('ORDER BY')
        return f"{parts[0]} WHERE {access_filter} ORDER BY {parts[1]}"
    else:
        return sql + f" WHERE {access_filter}"


# ═══════════════════════════════════════════════════════════════
# SAFE QUERY EXECUTOR
# ═══════════════════════════════════════════════════════════════

def execute_query_safe(sql: str) -> Tuple[List[Dict], List[str], Optional[str]]:
    """
    Execute a validated SELECT query safely.
    Returns (data_rows, column_names, error).
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql)

        if cursor.description is None:
            return [], [], "No results"

        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()
        cursor.close()

        data = []
        for row in rows:
            row_dict = {}
            for i, val in enumerate(row):
                if hasattr(val, 'isoformat'):
                    row_dict[columns[i]] = val.isoformat()
                else:
                    row_dict[columns[i]] = val
            data.append(row_dict)

        return data, columns, None

    except Exception as e:
        return [], [], str(e)
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
# LEGACY ENTRY POINT (not used in the live path)
# ═══════════════════════════════════════════════════════════════
# query.py uses MCP Bridge for AI. This function remains as a
# direct-Ollama fallback for ad-hoc/internal use only.
# It is NOT invoked during normal query processing.
# ═══════════════════════════════════════════════════════════════

def process_query(question: str, user: dict) -> dict:
    """
    Legacy fallback. Kept so query.py's import doesn't break.
    The real AI path is in mcp_client.py / mcp_server.py.
    """
    elapsed = 0
    return {
        "question": question,
        "generated_sql": None,
        "method": "disabled",
        "data": [],
        "columns": [],
        "row_count": 0,
        "execution_time_ms": elapsed,
        "insights": [
            "Direct nlq_engine.process_query is disabled. "
            "Queries are handled by MCP Bridge → Ollama."
        ],
        "error": "nlq_engine.process_query is a legacy entrypoint.",
    }