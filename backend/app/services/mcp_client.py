"""
MCP Client Bridge v4 - Database & Table Switching
===================================================
Supports:
  - Multiple databases (anandrathi, anandrathi_trading, etc.)
  - Multiple tables per database
  - MCP subprocess for main table, direct calls for others
  - Role-based access control

Flow: React → FastAPI → mcp_client → mcp_server → Ollama AI + SQL Server
"""

import os
import sys
import json
import asyncio
import time
import re
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.services.error_logger import log_error
from app.services.access_control import build_app_filter, inject_access_into_sql

MCP_SERVER_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "mcp_server.py"
)
# ═══════════════════════════════════════════════════════════════
# DATABASE & TABLE CONFIGURATION
# Single source of truth: db_config.json at backend root.
# Adding a new DB = edit JSON, restart backend. No code change.
# ═══════════════════════════════════════════════════════════════

_CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "db_config.json"
)


def _load_db_config() -> dict:
    """Load DB config from db_config.json. Raises if missing or malformed."""
    try:
        with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise RuntimeError(
            f"db_config.json not found at {_CONFIG_FILE}. "
            f"This file is required for multi-database support."
        )
    except json.JSONDecodeError as e:
        raise RuntimeError(f"db_config.json is malformed: {e}")


_CONFIG = _load_db_config()
DATABASES = _CONFIG.get("databases", {})
DEFAULT_DATABASE = _CONFIG.get("default_database", "anandrathi")


def get_available_databases() -> list:
    """Get list of all available databases from config."""
    return [
        {
            "database": db_name,
            "label": cfg.get("label", db_name),
            "description": cfg.get("description", ""),
        }
        for db_name, cfg in DATABASES.items()
    ]


def get_allowed_tables(database: str, user_role: str) -> list:
    """Get list of tables a user can query in a given database."""
    db_config = DATABASES.get(database, {})
    tables_cfg = db_config.get("tables", {})

    result = []
    for table_name, cfg in tables_cfg.items():
        access = cfg.get("access", "all")
        if access == "all" or (access == "admin" and user_role == "Admin"):
            result.append({
                "table_name": table_name,
                "label": cfg.get("label", table_name),
                "description": cfg.get("description", ""),
            })
    return result


def get_default_table(database: str) -> str:
    """Get the default table for a database."""
    return DATABASES.get(database, {}).get("default_table", "")


def get_server_for_db(database: str) -> str:
    """
    Get the SQL Server instance for a database (kept for backward compat).
    Returns empty string for non-SQL-Server DBs.
    """
    cfg = DATABASES.get(database, {})
    if cfg.get("db_type") == "sqlserver":
        return cfg.get("server", "")
    return ""


# ═══════════════════════════════════════════════════════════════
# MCP BRIDGE CLASS
# ═══════════════════════════════════════════════════════════════

class MCPBridge:

    def __init__(self):
        self.server_params = StdioServerParameters(
            command=sys.executable,
            args=[MCP_SERVER_PATH],
        )

    @asynccontextmanager
    async def _get_session(self):
        async with stdio_client(self.server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session

    async def _call_tool(self, tool_name: str, arguments: dict = None) -> str:
        async with self._get_session() as session:
            result = await session.call_tool(tool_name, arguments or {})
            if result.content:
                return result.content[0].text
            return ""

    # ───────────────────────────────────────────────────────────
    # MAIN ENTRY POINT
    # ───────────────────────────────────────────────────────────

    async def ask_question(
        self,
        question: str,
        user: dict = None,
        table_name: str = None,
        database: str = None,
        category: str = None,
    ) -> Dict[str, Any]:
        """
        Full pipeline: question → SQL → execute → results.
        Supports database switching and table switching.
        """
        start_time = time.time()
        db = database or DEFAULT_DATABASE
        server = get_server_for_db(db)

        # Validate database
        if db not in DATABASES:
            elapsed = int((time.time() - start_time) * 1000)
            return self._error_response(
                question, elapsed,
                f"Database '{db}' is not configured."
            )

        db_config = DATABASES[db]

        # Resolve category → list of tables (category mode)
        category_tables = []
        if category:
            cats = db_config.get("categories", {})
            if category not in cats:
                elapsed = int((time.time() - start_time) * 1000)
                return self._error_response(
                    question, elapsed,
                    f"Category '{category}' not found in {db_config.get('label', db)} database."
                )
            category_tables = cats[category].get("tables", [])
            # Use the category's default_table as "primary" for access filter purposes
            target_table = cats[category].get("default_table") or (category_tables[0] if category_tables else "")
        else:
            # Single-table mode (existing behavior)
            target_table = table_name or db_config.get("default_table", "")

        # Validate table exists in this database
        if target_table not in db_config["tables"]:
            elapsed = int((time.time() - start_time) * 1000)
            return self._error_response(
                question, elapsed,
                f"Table '{target_table}' not found in {db_config['label']} database."
            )

        # Check access level
        user_role = user.get("role", "") if user else ""
        table_config = db_config["tables"][target_table]
        if table_config["access"] == "admin" and user_role != "Admin":
            elapsed = int((time.time() - start_time) * 1000)
            return self._error_response(
                question, elapsed,
                f"Admin access required to query {table_config['label']}."
            )

        # Route: Use direct calls (avoids STDIO issues on Windows)
        # MCP subprocess path kept for future use / Claude Code
        return self._ask_question_direct(
            question, user, target_table, db, server,
            category=category, category_tables=category_tables,
        )

    # ───────────────────────────────────────────────────────────
    # DIRECT FUNCTION CALL PATH
    # ───────────────────────────────────────────────────────────

    def _ask_question_direct(
        self,
        question: str,
        user: dict = None,
        table_name: str = None,
        database: str = "anandrathi",
        server: str = r"GLADIATOR\SQLEXPRESS",
        category: str = None,
        category_tables: list = None,
    ) -> Dict[str, Any]:
        """
        Calls mcp_server functions directly.
        Handles database switching via connect_database tool.
        """
        start_time = time.time()

        try:
            from mcp_server import connect_database, generate_sql, execute_query

            # Step 1: Connect to the selected database
            connect_result = connect_database(database_name=database)
            if "FAILED" in connect_result:
                elapsed = int((time.time() - start_time) * 1000)
                return self._error_response(question, elapsed, f"Connection failed: {connect_result}")

            # Step 2: Generate SQL — use category mode if category provided
            if category and category_tables:
                sql_text = generate_sql(
                    question, "",
                    category_tables=",".join(category_tables),
                    category_name=category,
                )
            else:
                sql_text = generate_sql(question, "", table_name)
            generated_sql = self._extract_sql(sql_text)

            if not generated_sql:
                elapsed = int((time.time() - start_time) * 1000)
                return self._error_response(
                    question, elapsed,
                    f"Could not generate SQL. AI returned: {sql_text}"
                )

            # Step 3: Inject access control
            if user and database == "anandrathi":
                if category and category_tables:
                    # Category mode: use regex-based injection (handles JOINs)
                    modified_sql, err = inject_access_into_sql(generated_sql, user)
                    if err:
                        # Fail-closed: reject query
                        elapsed = int((time.time() - start_time) * 1000)
                        return self._error_response(question, elapsed, err)
                    generated_sql = modified_sql
                elif table_name == "CommunicationMaster":
                    # Single-table legacy path (unchanged)
                    generated_sql = self._inject_access_filter(generated_sql, user, database=database)

            # Step 4: Execute SQL
            exec_text = execute_query(generated_sql)
            data, columns, total_rows, truncated = self._parse_execution_result(exec_text)

            elapsed = int((time.time() - start_time) * 1000)

            # Get database label for display
            db_label = DATABASES.get(database, {}).get("label", database)

            insights = []
            if len(data) == 0:
                insights.append("No records found matching your query.")
            else:
                insights.append(f"Found {len(data)} records.")
            insights.append(f"Database: {db_label} | Table: {table_name}")

            return {
                "question": question,
                "generated_sql": generated_sql,
                "method": "mcp",
                "data": data,
                "columns": columns,
                "row_count": len(data),
                "total_rows": total_rows,
                "truncated": truncated,
                "execution_time_ms": elapsed,
                "insights": insights,
                "error": None,
            }

        except Exception as e:
            elapsed = int((time.time() - start_time) * 1000)
            log_error("MCP_DIRECT", str(e), endpoint="ask_question_direct")
            return self._error_response(question, elapsed, str(e))

    # ───────────────────────────────────────────────────────────
    # MCP SUBPROCESS PATH (kept for Claude Code / MCP Inspector)
    # ───────────────────────────────────────────────────────────

    async def _ask_question_mcp(
        self,
        question: str,
        user: dict,
        target_table: str,
        server: str,
        database: str,
    ) -> Dict[str, Any]:
        """Route through MCP subprocess via STDIO protocol."""
        start_time = time.time()

        try:
            async with self._get_session() as session:
                connect_result = await session.call_tool(
                    "connect_database",
                    {"database_name": database}
                )
                connect_text = connect_result.content[0].text if connect_result.content else ""

                if "FAILED" in connect_text:
                    elapsed = int((time.time() - start_time) * 1000)
                    return self._error_response(question, elapsed, f"Connection failed: {connect_text}")

                schema_result = await session.call_tool(
                    "get_schema", {"table_name": target_table}
                )
                schema_text = schema_result.content[0].text if schema_result.content else ""

                sql_result = await session.call_tool(
                    "generate_sql",
                    {"question": question, "schema_text": schema_text, "table_name": target_table}
                )
                sql_text = sql_result.content[0].text if sql_result.content else ""
                generated_sql = self._extract_sql(sql_text)

                if not generated_sql:
                    elapsed = int((time.time() - start_time) * 1000)
                    return self._error_response(question, elapsed, f"Could not generate SQL. AI returned: {sql_text}")

                if user and target_table == "CommunicationMaster":
                    generated_sql = self._inject_access_filter(generated_sql, user, database=database)

                exec_result = await session.call_tool("execute_query", {"sql": generated_sql})
                exec_text = exec_result.content[0].text if exec_result.content else ""
                data, columns, total_rows, truncated = self._parse_execution_result(exec_text)
                elapsed = int((time.time() - start_time) * 1000)

                return {
                    "question": question,
                    "generated_sql": generated_sql,
                    "method": "mcp",
                    "data": data,
                    "columns": columns,
                    "row_count": len(data),
                    "total_rows": total_rows,
                    "truncated": truncated,
                    "execution_time_ms": elapsed,
                    "insights": [f"Found {len(data)} records.", f"Table: {target_table}"],
                    "error": None,
                }

        except Exception as e:
            elapsed = int((time.time() - start_time) * 1000)
            log_error("MCP_BRIDGE", str(e), endpoint="ask_question_mcp")
            return self._error_response(question, elapsed, str(e))

    # ───────────────────────────────────────────────────────────
    # INDIVIDUAL TOOL WRAPPERS
    # ───────────────────────────────────────────────────────────

    async def connect_database(self, database_name: str = "anandrathi") -> str:
        return await self._call_tool("connect_database", {"database_name": database_name})

    async def get_schema(self, table_name: str = "") -> str:
        return await self._call_tool("get_schema", {"table_name": table_name})

    async def generate_sql(self, question: str, schema_text: str = "") -> str:
        return await self._call_tool("generate_sql", {"question": question, "schema_text": schema_text})

    async def execute_query(self, sql: str, max_rows: int = 50) -> str:
        return await self._call_tool("execute_query", {"sql": sql, "max_rows": max_rows})
    
    def execute_for_export(self, sql: str, database: str, max_rows: int = 50000) -> tuple:
        """
        Execute SQL with a high row cap for CSV export.
        Uses direct function calls (avoids MCP STDIO issues on Windows).
        Returns (data, columns, total_rows, truncated, error).
        """
        try:
            from mcp_server import connect_database, execute_query

            connect_result = connect_database(database_name=database)
            if "FAILED" in connect_result:
                return [], [], 0, False, f"Connection failed: {connect_result}"

            exec_text = execute_query(sql, max_rows=max_rows)
            data, columns, total, truncated = self._parse_execution_result(exec_text)
            return data, columns, total, truncated, None
        except Exception as e:
            import sys, traceback
            tb_str = traceback.format_exc()
            print(f"\n═══ EXPORT DIRECT EXCEPTION ═══\n{tb_str}\n═══════════════════════════\n", file=sys.stderr, flush=True)
            return [], [], 0, False, f"{type(e).__name__}: {str(e)}"

    # ───────────────────────────────────────────────────────────
    # HELPERS
    # ───────────────────────────────────────────────────────────

    def _extract_sql(self, ai_response: str) -> Optional[str]:
        if not ai_response:
            return None
        if "Generated SQL:" in ai_response:
            sql = ai_response.split("Generated SQL:", 1)[1].strip()
        elif ai_response.upper().strip().startswith("SELECT"):
            sql = ai_response.strip()
        else:
            return None
        sql = sql.split(';')[0].strip()
        if sql.upper().startswith("SELECT"):
            return sql
        return None

    def _inject_access_filter(self, sql: str, user: dict, database: str = None) -> str:
        """
        Inject access control filter based on ApplicationAccessMaster.
        Admin (role=Admin + no access rows) → SQL unchanged.
        Scoped user → AND ApplicationId IN (...) added.
        Blocked user → AND 1=0 added (fail-safe).

        Only applies to the Communications DB (anandrathi). Other DBs
        (Trading on Postgres) don't have ApplicationId column.
        """
        # Only apply to the Communications database
        if database and database != "anandrathi":
            return sql

        access_filter, scope = build_app_filter(user, column="ApplicationId")
        if not access_filter:
            return sql  # admin, no change

        sql_upper = sql.upper()
        if "WHERE" in sql_upper:
            where_pos = sql_upper.index("WHERE") + 5
            sql = sql[:where_pos] + f" {access_filter} AND" + sql[where_pos:]
        else:
            insert_before = None
            for keyword in ["GROUP BY", "ORDER BY", "HAVING"]:
                if keyword in sql_upper:
                    pos = sql_upper.index(keyword)
                    if insert_before is None or pos < insert_before:
                        insert_before = pos
            if insert_before:
                sql = sql[:insert_before] + f"WHERE {access_filter} " + sql[insert_before:]
            else:
                sql = sql + f" WHERE {access_filter}"
        return sql

    def _parse_execution_result(self, exec_text: str) -> tuple:
        """Parse structured JSON from mcp_server. Returns (data, columns, total, truncated)."""
        if not exec_text:
            return [], [], 0, False
        try:
            parsed = json.loads(exec_text)
        except (json.JSONDecodeError, ValueError):
            return [], [], 0, False
        if parsed.get("status") != "ok":
            return [], [], 0, False
        return (
            parsed.get("rows", []),
            parsed.get("columns", []),
            parsed.get("total", 0),
            parsed.get("truncated", False),
        )

    def _error_response(self, question: str, elapsed: int, error: str) -> dict:
        return {
            "question": question,
            "generated_sql": None,
            "method": "mcp",
            "data": [],
            "columns": [],
            "row_count": 0,
            "total_rows": 0,
            "truncated": False,
            "execution_time_ms": elapsed,
            "insights": [f"Error: {error}"],
            "error": error,
        }


# ═══════════════════════════════════════════════════════════════
# SINGLETON
# ═══════════════════════════════════════════════════════════════

mcp_bridge = MCPBridge()