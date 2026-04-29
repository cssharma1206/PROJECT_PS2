"""
Database Service - Centralized database connection management.

Two connections:
  - get_db_connection()           SQL Server (anandrathi)         — Communications
  - get_trading_db_connection()   PostgreSQL (anandrathi_trading) — Trading

Both read their config from db_config.json (single source of truth, same file
the MCP server uses). This avoids drift between dashboard SQL and query-mode SQL.
"""

import json
import os
import pyodbc
import pandas as pd
from app.config import get_connection_string

# psycopg2 only required for Trading endpoints
try:
    import psycopg2
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False


# ─── SQL SERVER (Communications) ─────────────────────────────────────────

def get_db_connection():
    """Get a fresh SQL Server connection (anandrathi). Used by Communications endpoints."""
    return pyodbc.connect(get_connection_string())


def execute_query(sql: str, params: tuple = None) -> pd.DataFrame:
    """Execute a SELECT query and return results as a DataFrame."""
    conn = get_db_connection()
    try:
        if params:
            df = pd.read_sql(sql, conn, params=params)
        else:
            df = pd.read_sql(sql, conn)
        return df
    finally:
        conn.close()


def execute_non_query(sql: str, params: tuple = None) -> bool:
    """Execute INSERT/UPDATE/DELETE. Returns True on success."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        conn.commit()
        cursor.close()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute_scalar(sql: str, params: tuple = None):
    """Execute a query and return the first column of the first row."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        row = cursor.fetchone()
        cursor.close()
        return row[0] if row else None
    finally:
        conn.close()


# ─── POSTGRESQL (Trading) ────────────────────────────────────────────────

# Resolve the same db_config.json the MCP server uses.
# Path: backend/db_config.json — two levels up from app/services/.
_CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "db_config.json",
)


def _load_trading_config() -> dict:
    """Read the anandrathi_trading config block from db_config.json."""
    try:
        with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg.get("databases", {}).get("anandrathi_trading", {})
    except Exception as e:
        raise RuntimeError(
            f"Could not load anandrathi_trading config from {_CONFIG_FILE}: {e}"
        )


def get_trading_db_connection():
    """
    Get a fresh PostgreSQL connection (anandrathi_trading).
    Used by Trading dashboard endpoints.

    Reads connection params from db_config.json so config is centralised.
    """
    if not PSYCOPG2_AVAILABLE:
        raise RuntimeError(
            "psycopg2 not installed. Run: pip install psycopg2-binary"
        )

    cfg = _load_trading_config()
    if not cfg:
        raise RuntimeError(
            "No 'anandrathi_trading' block found in db_config.json"
        )

    return psycopg2.connect(
        host=cfg["host"],
        port=cfg.get("port", 5432),
        database=cfg["database"],
        user=cfg["username"],
        password=cfg["password"],
    )