"""
═══════════════════════════════════════════════════════════════════
MCP SERVER - Anand Rathi Communications Intelligence Platform
═══════════════════════════════════════════════════════════════════

Day 9: MCP Project Setup (as per 15-day plan)

4 Tools:
  1. connect_database  — connect to a SQL Server database
  2. get_schema        — read table structure from INFORMATION_SCHEMA
  3. execute_query     — run a validated SELECT query
  4. generate_sql      — use Ollama AI to convert question to SQL

Run with:
  python mcp_server.py

Test with MCP Inspector:
  mcp dev mcp_server.py

IMPORTANT: This is a STDIO server — do NOT use print().
Use print(..., file=sys.stderr) for debug output.
"""

import sys
import json
import re
import pyodbc
import requests
from mcp.server.fastmcp import FastMCP


# ═══════════════════════════════════════════════════════════════
# CREATE MCP SERVER
# ═══════════════════════════════════════════════════════════════

mcp = FastMCP("anand-rathi-db")

# ═══════════════════════════════════════════════════════════════
# DATABASE CONFIG
# ═══════════════════════════════════════════════════════════════

DB_CONFIG = {
    "driver": "{ODBC Driver 17 for SQL Server}",
    "server": r"GLADIATOR\SQLEXPRESS",
    "database": "anandrathi",
    "trusted_connection": "yes",
}

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "gemma3:4b"


def _get_connection():
    """Create a database connection."""
    return pyodbc.connect(
        f"DRIVER={DB_CONFIG['driver']};"
        f"SERVER={DB_CONFIG['server']};"
        f"DATABASE={DB_CONFIG['database']};"
        f"Trusted_Connection={DB_CONFIG['trusted_connection']};"
    )


def _validate_sql(sql: str) -> tuple:
    """Check if SQL is safe. Returns (is_safe, reason)."""
    if not sql:
        return False, "Empty SQL"
    sql_upper = sql.upper().strip()
    if not sql_upper.startswith("SELECT"):
        return False, "Only SELECT queries allowed"
    dangerous = ['DROP', 'DELETE', 'INSERT', 'UPDATE', 'ALTER',
                 'CREATE', 'EXEC', 'EXECUTE', 'TRUNCATE']
    for word in dangerous:
        if re.search(rf'\b{word}\b', sql_upper):
            return False, f"Blocked: {word} not allowed"
    return True, "Safe"


# ═══════════════════════════════════════════════════════════════
# TOOL 1: connect_database
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
def connect_database(
    server: str = r"GLADIATOR\SQLEXPRESS",
    database: str = "anandrathi"
) -> str:
    """
    Connect to a SQL Server database.
    Call this first before using other tools.
    Default connects to Anand Rathi's anandrathi database.

    Args:
        server: SQL Server instance name
        database: Database name to connect to
    """
    DB_CONFIG["server"] = server
    DB_CONFIG["database"] = database

    try:
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        return f"Connected successfully to {server} / {database}"
    except Exception as e:
        return f"Connection FAILED: {str(e)}"


# ═══════════════════════════════════════════════════════════════
# TOOL 2: get_schema
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
def get_schema(table_name: str = "") -> str:
    """
    Get the table structure (columns, data types, sample values)
    from the connected database. Reads LIVE from INFORMATION_SCHEMA.COLUMNS.
    Schema is NEVER hardcoded — always fresh from the database.

    Args:
        table_name: Specific table name, or empty for all main tables
    """
    try:
        conn = _get_connection()
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
            cursor.execute("""
                SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, IS_NULLABLE,
                       CHARACTER_MAXIMUM_LENGTH
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME IN (
                    'CommunicationsRequestStatus', 'Users_v2', 'Roles'
                )
                ORDER BY TABLE_NAME, ORDINAL_POSITION
            """)

        rows = cursor.fetchall()

        schema_lines = []
        current_table = None
        for table, col, dtype, nullable, max_len in rows:
            if table != current_table:
                if current_table:
                    schema_lines.append("")
                schema_lines.append(f"Table: {table}")
                schema_lines.append("Columns:")
                current_table = table

            type_str = f"{dtype}({max_len})" if max_len and max_len > 0 else dtype
            null_str = "nullable" if nullable == "YES" else "required"
            schema_lines.append(f"  - {col} ({type_str}, {null_str})")

        # Sample values
        if not table_name or table_name == "CommunicationsRequestStatus":
            schema_lines.append("")
            schema_lines.append("Sample values:")
            cursor.execute("SELECT DISTINCT LastStatus FROM CommunicationsRequestStatus")
            statuses = [r[0] for r in cursor.fetchall()]
            schema_lines.append(f"  LastStatus: {', '.join(statuses)}")

            cursor.execute("SELECT DISTINCT TOP 5 Sender FROM CommunicationsRequestStatus")
            senders = [r[0] for r in cursor.fetchall()]
            schema_lines.append(f"  Senders: {', '.join(senders)}")

            cursor.execute("SELECT COUNT(*) FROM CommunicationsRequestStatus")
            total = cursor.fetchone()[0]
            schema_lines.append(f"  Total rows: {total}")

        cursor.close()
        conn.close()
        return "\n".join(schema_lines)

    except Exception as e:
        return f"Schema read error: {str(e)}"


# ═══════════════════════════════════════════════════════════════
# TOOL 3: execute_query
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
def execute_query(sql: str) -> str:
    """
    Execute a SQL SELECT query on the connected database and return results.
    Only SELECT queries are allowed — INSERT/UPDATE/DELETE are blocked.

    Args:
        sql: The SQL SELECT query to execute
    """
    is_safe, reason = _validate_sql(sql)
    if not is_safe:
        return f"BLOCKED: {reason}"

    try:
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute(sql)

        if cursor.description is None:
            cursor.close()
            conn.close()
            return "Query executed but returned no results."

        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        result_lines = [f"Columns: {', '.join(columns)}"]
        result_lines.append(f"Rows returned: {len(rows)}")
        result_lines.append("")

        for row in rows[:50]:
            row_data = {}
            for j, val in enumerate(row):
                if hasattr(val, 'isoformat'):
                    row_data[columns[j]] = val.isoformat()
                else:
                    row_data[columns[j]] = val
            result_lines.append(json.dumps(row_data, default=str))

        if len(rows) > 50:
            result_lines.append(f"... ({len(rows) - 50} more rows)")

        return "\n".join(result_lines)

    except Exception as e:
        return f"SQL Error: {str(e)}"


# ═══════════════════════════════════════════════════════════════
# TOOL 4: generate_sql
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
def generate_sql(question: str, schema_text: str = "") -> str:
    """
    Generate a SQL query from a natural language question.
    Uses Ollama AI (Qwen 2.5:3B on localhost:11434) to convert
    English questions into SQL Server queries.

    Args:
        question: Natural language question like 'show failed emails last 7 days'
        schema_text: Schema from get_schema tool. If empty, reads automatically.
    """
    if not schema_text:
        schema_text = get_schema("CommunicationsRequestStatus")

    prompt = f"""You are a SQL Server expert. Generate ONLY a short, clean SQL query.

The ONLY table in this database is: CommunicationsRequestStatus

{schema_text}

RULES:
- ALWAYS include FROM CommunicationsRequestStatus in every query.
- Output ONLY the SQL query. No explanations. No markdown.
- Keep queries SHORT and SIMPLE. Maximum 5-6 lines.
- Use TOP instead of LIMIT
- For NULL checks: column IS NULL or column IS NOT NULL
- Status values: 'SENT', 'FAILED', 'PENDING', 'CREATED', 'SUBMITTED', 'DELIVERED'
- Do NOT add unnecessary conditions. Only what the question asks for.

EXAMPLES:
Q: how many emails have null in bccdata
SQL: SELECT COUNT(*) AS Total FROM CommunicationsRequestStatus WHERE BccData IS NULL

Q: show failed emails
SQL: SELECT TOP 50 Id, Receiver, Sender, LastStatus FROM CommunicationsRequestStatus WHERE LastStatus = 'FAILED' ORDER BY SubmitDate DESC

Q: emails by status
SQL: SELECT LastStatus, COUNT(*) AS Count FROM CommunicationsRequestStatus GROUP BY LastStatus ORDER BY Count DESC

Q: which sender has the most failed emails
SQL: SELECT TOP 10 Sender, COUNT(*) AS FailCount FROM CommunicationsRequestStatus WHERE LastStatus = 'FAILED' GROUP BY Sender ORDER BY FailCount DESC

Question: {question}
SQL:"""

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_predict": 200,
                    "repeat_penalty": 1.3,
                    "stop": ["\n\n", "Question:", "Q:"],
                },
            },
            timeout=120,
        )

        if response.status_code != 200:
            return f"Ollama error: HTTP {response.status_code}"

        sql = response.json().get("response", "").strip()
        sql = re.sub(r'```sql\s*|```\s*', '', sql, flags=re.IGNORECASE)
        sql = re.sub(r'^.*?SELECT', 'SELECT', sql, flags=re.IGNORECASE | re.DOTALL)
        sql = sql.split(';')[0].strip()

        # Kill repeated lines (the Qwen 3B hallucination problem)
        lines = sql.split('\n')
        clean_lines = []
        seen = set()
        for line in lines:
            normalized = line.strip().lower()
            if normalized and normalized in seen and 'AND' in line.upper():
                break  # Stop at first repeated AND condition
            seen.add(normalized)
            clean_lines.append(line)
        sql = '\n'.join(clean_lines).strip()

        if not sql.upper().startswith('SELECT'):
            return "AI could not generate valid SQL. Try rephrasing."

        is_safe, reason = _validate_sql(sql)
        if not is_safe:
            return f"Generated SQL blocked: {reason}"

        return f"Generated SQL:\n{sql}"

    except requests.Timeout:
        return "Ollama timed out. Make sure it's running: ollama serve"
    except requests.ConnectionError:
        return "Cannot connect to Ollama. Start it with: ollama serve"
    except Exception as e:
        return f"Error: {str(e)}"


# ═══════════════════════════════════════════════════════════════
# RUN
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("Starting Anand Rathi MCP Server...", file=sys.stderr)
    print("Tools: connect_database, get_schema, execute_query, generate_sql", file=sys.stderr)
    mcp.run()