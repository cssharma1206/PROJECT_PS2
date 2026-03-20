"""
Database Service - Centralized database connection management.
Every part of the app uses get_db_connection() from here.
"""

import pyodbc
import pandas as pd
from app.config import get_connection_string


def get_db_connection():
    """Get a fresh database connection. Used by all services."""
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
