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


# ═══════════════════════════════════════════════════════════════
# MCP SERVER LOCATION
# ═══════════════════════════════════════════════════════════════

MCP_SERVER_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "mcp_server.py"
)


# ═══════════════════════════════════════════════════════════════
# DATABASE & TABLE CONFIGURATION
# ═══════════════════════════════════════════════════════════════

DATABASES = {
    "anandrathi": {
        "label": "Communications",
        "description": "Email & communication tracking system",
        "server": r"GLADIATOR\SQLEXPRESS",
        "tables": {
            "CommunicationsRequestStatus": {
                "label": "Communications",
                "description": "Email communications and delivery status",
                "access": "all",
            },
            "QueryLog": {
                "label": "Query Logs",
                "description": "History of all queries executed",
                "access": "admin",
            },
            "ErrorLog": {
                "label": "Error Logs",
                "description": "Application errors and exceptions",
                "access": "admin",
            },
        },
        "default_table": "CommunicationsRequestStatus",
    },
    "anandrathi_trading": {
        "label": "Trading",
        "description": "Stock trading & portfolio management",
        "server": r"GLADIATOR\SQLEXPRESS",
        "tables": {
            "TradeHistory": {
                "label": "Trade History",
                "description": "Stock trades, orders, and settlements",
                "access": "all",
            },
        },
        "default_table": "TradeHistory",
    },
}

DEFAULT_DATABASE = "anandrathi"


def get_available_databases() -> list:
    """Get list of all available databases."""
    dbs = []
    for db_name, config in DATABASES.items():
        dbs.append({
            "database": db_name,
            "label": config["label"],
            "description": config["description"],
        })
    return dbs


def get_allowed_tables(database: str, user_role: str) -> list:
    """Get list of tables a user can query in a given database."""
    db_config = DATABASES.get(database)
    if not db_config:
        return []

    tables = []
    for table_name, config in db_config["tables"].items():
        if config["access"] == "all" or (config["access"] == "admin" and user_role == "Admin"):
            tables.append({
                "table_name": table_name,
                "label": config["label"],
                "description": config["description"],
            })
    return tables


def get_default_table(database: str) -> str:
    """Get the default table for a database."""
    db_config = DATABASES.get(database)
    if db_config:
        return db_config["default_table"]
    return ""


def get_server_for_db(database: str) -> str:
    """Get the SQL Server instance for a database."""
    db_config = DATABASES.get(database)
    if db_config:
        return db_config["server"]
    return r"GLADIATOR\SQLEXPRESS"


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

        # Determine target table
        db_config = DATABASES[db]
        target_table = table_name or db_config["default_table"]

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
        return self._ask_question_direct(question, user, target_table, db, server)

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
    ) -> Dict[str, Any]:
        """
        Calls mcp_server functions directly.
        Handles database switching via connect_database tool.
        """
        start_time = time.time()

        try:
            from mcp_server import connect_database, generate_sql, execute_query

            # Step 1: Connect to the selected database
            connect_result = connect_database(server=server, database=database)
            if "FAILED" in connect_result:
                elapsed = int((time.time() - start_time) * 1000)
                return self._error_response(question, elapsed, f"Connection failed: {connect_result}")

            # Step 2: Generate SQL (dynamic prompt reads schema from connected DB)
            sql_text = generate_sql(question, "", table_name)
            generated_sql = self._extract_sql(sql_text)

            if not generated_sql:
                elapsed = int((time.time() - start_time) * 1000)
                return self._error_response(
                    question, elapsed,
                    f"Could not generate SQL. AI returned: {sql_text}"
                )

            # Step 3: Inject access control (only for Communications main table)
            if user and database == "anandrathi" and table_name == "CommunicationsRequestStatus":
                generated_sql = self._inject_access_filter(generated_sql, user)

            # Step 4: Execute SQL
            exec_text = execute_query(generated_sql)
            data, columns = self._parse_execution_result(exec_text)

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
                    {"server": server, "database": database}
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

                if user and target_table == "CommunicationsRequestStatus":
                    generated_sql = self._inject_access_filter(generated_sql, user)

                exec_result = await session.call_tool("execute_query", {"sql": generated_sql})
                exec_text = exec_result.content[0].text if exec_result.content else ""

                data, columns = self._parse_execution_result(exec_text)
                elapsed = int((time.time() - start_time) * 1000)

                return {
                    "question": question,
                    "generated_sql": generated_sql,
                    "method": "mcp",
                    "data": data,
                    "columns": columns,
                    "row_count": len(data),
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

    async def connect_database(self, server: str = r"GLADIATOR\SQLEXPRESS", database: str = "anandrathi") -> str:
        return await self._call_tool("connect_database", {"server": server, "database": database})

    async def get_schema(self, table_name: str = "") -> str:
        return await self._call_tool("get_schema", {"table_name": table_name})

    async def generate_sql(self, question: str, schema_text: str = "") -> str:
        return await self._call_tool("generate_sql", {"question": question, "schema_text": schema_text})

    async def execute_query(self, sql: str) -> str:
        return await self._call_tool("execute_query", {"sql": sql})

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

    def _inject_access_filter(self, sql: str, user: dict) -> str:
        role = user.get("role", "")
        app_id = user.get("application_id")

        if role == "Admin":
            return sql

        if app_id and role in ("RM_Head", "RM", "RM_Head2", "RM2", "RM3"):
            access_filter = f"ReferenceApplicationId = {app_id}"
        else:
            username = user.get("username", "")
            access_filter = f"Receiver LIKE '%{username}%'"

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
        if not exec_text or "BLOCKED" in exec_text or "Error" in exec_text:
            return [], []

        lines = exec_text.strip().split('\n')
        columns = []
        data = []

        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith("Columns:"):
                columns = [c.strip() for c in line.replace("Columns:", "").split(",")]
                continue
            if line.startswith("Rows returned:") or line.startswith("..."):
                continue
            try:
                row = json.loads(line)
                if isinstance(row, dict):
                    data.append(row)
            except (json.JSONDecodeError, ValueError):
                continue
        return data, columns

    def _error_response(self, question: str, elapsed: int, error: str) -> dict:
        return {
            "question": question,
            "generated_sql": None,
            "method": "mcp",
            "data": [],
            "columns": [],
            "row_count": 0,
            "execution_time_ms": elapsed,
            "insights": [f"Error: {error}"],
            "error": error,
        }


# ═══════════════════════════════════════════════════════════════
# SINGLETON
# ═══════════════════════════════════════════════════════════════

mcp_bridge = MCPBridge()