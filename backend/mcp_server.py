"""
═══════════════════════════════════════════════════════════════════
MCP SERVER v3.1 - Anand Rathi Communications Intelligence Platform
═══════════════════════════════════════════════════════════════════

Day 11: Fully dynamic prompt — optimized for speed.

Changes from v3:
  - Smarter sampling: skips columns with long values (JSON, blobs)
  - Skips empty string samples
  - Fewer DB queries during prompt building
  - Increased Ollama timeout to 180s
  - Leaner prompt = faster AI response

4 Tools:
  1. connect_database  — connect to a SQL Server database
  2. get_schema        — read table structure from INFORMATION_SCHEMA
  3. execute_query     — run a validated SELECT query
  4. generate_sql      — use Ollama AI to convert question to SQL

Run with:  python mcp_server.py
Test with: mcp dev mcp_server.py
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
OLLAMA_TIMEOUT = 180  # increased from 120


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
    Get table structure from INFORMATION_SCHEMA. Always live, never cached.

    Args:
        table_name: Specific table name, or empty for all user tables
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
                WHERE TABLE_SCHEMA = 'dbo'
                  AND TABLE_NAME NOT IN ('sysdiagrams')
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
    Execute a SQL SELECT query and return results.
    Only SELECT queries are allowed.

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
# DYNAMIC PROMPT BUILDER (optimized v3.1)
# ═══════════════════════════════════════════════════════════════

# Columns to skip when sampling (they have long/noisy values)
SKIP_SAMPLE_COLUMNS = {'RequestData', 'Body', 'Subject', 'Gu_id',
                       'TrackingId', 'Password', 'PasswordHash'}


def _get_table_names() -> list:
    """Get all user table names from the connected database."""
    try:
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT TABLE_NAME
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_TYPE = 'BASE TABLE'
              AND TABLE_SCHEMA = 'dbo'
              AND TABLE_NAME NOT IN ('sysdiagrams')
            ORDER BY TABLE_NAME
        """)
        tables = [r[0] for r in cursor.fetchall()]
        cursor.close()
        conn.close()
        return tables
    except Exception:
        return []


def _get_schema_and_samples(table_name: str) -> tuple:
    """
    Get columns AND sample values in ONE database connection.
    Returns (columns_list, samples_dict, total_rows).
    This is much faster than separate calls.
    """
    columns = []
    samples = {}
    total_rows = 0

    try:
        conn = _get_connection()
        cursor = conn.cursor()

        # Get columns
        cursor.execute("""
            SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = ?
            ORDER BY ORDINAL_POSITION
        """, (table_name,))
        columns = [(r[0], r[1], r[2]) for r in cursor.fetchall()]

        # Get total rows
        cursor.execute(f"SELECT COUNT(*) FROM [{table_name}]")
        total_rows = cursor.fetchone()[0]

        # Sample only useful columns (one query per column, skip noisy ones)
        for col_name, col_type, _ in columns:
            # Skip columns that have long/noisy values
            if col_name in SKIP_SAMPLE_COLUMNS:
                continue

            # Only sample short string columns and small int columns
            if col_type not in ('nvarchar', 'varchar', 'int', 'smallint', 'tinyint'):
                continue

            try:
                cursor.execute(f"""
                    SELECT DISTINCT TOP 10 [{col_name}]
                    FROM [{table_name}]
                    WHERE [{col_name}] IS NOT NULL AND CAST([{col_name}] AS NVARCHAR(100)) != ''
                      AND LEN(CAST([{col_name}] AS NVARCHAR(MAX))) < 50
                    ORDER BY [{col_name}]
                """)
                values = [str(r[0]).strip() for r in cursor.fetchall()]
                # Only include if there are meaningful values and not too many
                if values and len(values) <= 10:
                    samples[col_name] = values
            except Exception:
                continue

        cursor.close()
        conn.close()
    except Exception:
        pass

    return columns, samples, total_rows


def _build_dynamic_prompt(question: str, table_name: str) -> str:
    """
    Build the AI prompt dynamically from live database schema.
    Nothing is hardcoded. If the table changes, the prompt changes.
    """
    # Get everything in one DB connection
    columns, samples, total_rows = _get_schema_and_samples(table_name)

    if not columns:
        return None

    # Categorize columns
    col_names = []
    col_lines = []
    date_cols = []
    status_cols = []
    nullable_cols = []
    person_cols = []

    for col_name, col_type, nullable in columns:
        col_names.append(col_name)
        col_lines.append(f"  - {col_name} ({col_type})")

        if col_type in ('datetime', 'datetime2', 'date'):
            date_cols.append(col_name)
        if nullable == "YES":
            nullable_cols.append(col_name)
        if any(w in col_name.lower() for w in ['receiver', 'sender', 'email', 'name', 'user']):
            person_cols.append(col_name)
        # Detect status columns: string type + few distinct values
        if col_name in samples and col_type in ('nvarchar', 'varchar'):
            if len(samples[col_name]) <= 10:
                status_cols.append(col_name)

    # Build sample values section (compact)
    sample_lines = []
    for col_name, values in samples.items():
        sample_lines.append(f"  {col_name}: {', '.join(values)}")

    # Build rules
    rules = [
        f"- Table: {table_name}",
        f"- ALWAYS use FROM {table_name}",
        "- Output ONLY SQL. No text. No markdown. No backticks.",
        "- SQL Server syntax: TOP (not LIMIT), GETDATE(), DATEADD(), DATEPART()",
        f"- EXACT column names: {', '.join(col_names)}",
        "- NEVER invent column names. ONLY use columns listed above.",
        "- For counting rows, ALWAYS use COUNT(*), NEVER use COUNT(column_name) — COUNT(column) skips NULLs.",
    ]

    if date_cols:
        dc = date_cols[0]
        rules.append(f"- Date column: {dc}. Use FORMAT({dc}, 'dd-MMM-yyyy') for display.")
        rules.append(f"- Date range: {dc} >= DATEADD(day, -7, GETDATE())")
        rules.append(f"- Weekends: DATEPART(WEEKDAY, {dc}) IN (1, 7)")

    for sc in status_cols:
        vals = samples.get(sc, [])
        if vals:
            quoted = ', '.join([f"'{v}'" for v in vals])
            rules.append(f"- {sc} values: {quoted}")
            val_lower = [v.lower() for v in vals]
            if 'sent' in val_lower:
                rules.append(f"- 'successful'/'delivered' emails = {sc} = 'SENT'")

    # Build 4-5 concise examples (not 8 — keeps prompt short)
    examples = ["EXAMPLES:"]
    t = table_name
    id_col = col_names[0]
    dc = date_cols[0] if date_cols else None
    sc = status_cols[0] if status_cols else None
    top5 = ', '.join(col_names[:5])

    if sc and sc in samples:
        val = samples[sc][0]
        order = f"ORDER BY {dc} DESC" if dc else f"ORDER BY {id_col} DESC"
        examples.append(f"Q: show {val.lower()} records")
        examples.append(f"SQL: SELECT TOP 50 {top5} FROM {t} WHERE {sc} = '{val}' {order}")
        examples.append("")

    if sc:
        examples.append(f"Q: count by {sc.lower()}")
        examples.append(f"SQL: SELECT {sc}, COUNT(*) AS Count FROM {t} GROUP BY {sc} ORDER BY Count DESC")
        examples.append("")

    if nullable_cols:
        nc = nullable_cols[0]
        examples.append(f"Q: how many have null in {nc.lower()}")
        examples.append(f"SQL: SELECT COUNT(*) AS Total FROM {t} WHERE {nc} IS NULL")
        examples.append("")

    if nullable_cols and len(nullable_cols) > 1:
        nc2 = nullable_cols[1]
        examples.append(f"Q: count rows where {nc2.lower()} is null")
        examples.append(f"SQL: SELECT COUNT(*) AS Total FROM {t} WHERE {nc2} IS NULL")
        examples.append("")

    if dc:
        examples.append(f"Q: records from last 7 days")
        examples.append(f"SQL: SELECT TOP 50 {top5} FROM {t} WHERE {dc} >= DATEADD(day, -7, GETDATE()) ORDER BY {dc} DESC")
        examples.append("")

    if person_cols:
        pc = person_cols[0]
        examples.append(f"Q: top {pc.lower()}s")
        examples.append(f"SQL: SELECT TOP 20 {pc}, COUNT(*) AS Total FROM {t} GROUP BY {pc} ORDER BY Total DESC")
        examples.append("")

    # Assemble prompt
    prompt = f"""You are a SQL Server query generator. Output ONLY raw SQL. Nothing else.

TABLE: {table_name} ({total_rows} rows)

COLUMNS:
{chr(10).join(col_lines)}

SAMPLE VALUES:
{chr(10).join(sample_lines) if sample_lines else '  (none)'}

RULES:
{chr(10).join(rules)}

{chr(10).join(examples)}

Question: {question}
SQL:"""

    return prompt


# ═══════════════════════════════════════════════════════════════
# TOOL 4: generate_sql (FULLY DYNAMIC PROMPT)
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
def generate_sql(question: str, schema_text: str = "", table_name: str = "") -> str:
    """
    Generate a SQL query from a natural language question.
    Prompt is built dynamically from live database schema.

    Args:
        question: Natural language question
        schema_text: Optional. If empty, reads live from DB.
        table_name: Optional. Which table to query. If empty, auto-detects.
    """
    # Use provided table_name, or auto-detect
    if table_name:
        target_table = table_name
    else:
        tables = _get_table_names()
        skip_tables = {'users', 'users_v2', 'roles', 'token',
                       'accesslog', 'sysdiagrams'}
        target_table = None
        for t in tables:
            if t.lower() not in skip_tables:
                target_table = t
                break
        if not target_table:
            target_table = tables[0] if tables else "CommunicationsRequestStatus"

    # Build prompt dynamically
    prompt = _build_dynamic_prompt(question, target_table)

    if not prompt:
        return "Could not read schema. Is the database connected?"

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_predict": 120,
                    "repeat_penalty": 1.3,
                    "stop": ["\n\n", "Question:", "Q:", "Note:", "Explanation:"],
                },
            },
            timeout=OLLAMA_TIMEOUT,
        )

        if response.status_code != 200:
            return f"Ollama error: HTTP {response.status_code}"

        sql = response.json().get("response", "").strip()
        sql = re.sub(r'```sql\s*|```\s*', '', sql, flags=re.IGNORECASE)
        sql = re.sub(r'^.*?SELECT', 'SELECT', sql, flags=re.IGNORECASE | re.DOTALL)
        sql = sql.split(';')[0].strip()

        # Kill repeated lines (hallucination fix)
        lines = sql.split('\n')
        clean_lines = []
        seen = set()
        for line in lines:
            normalized = line.strip().lower()
            if normalized and normalized in seen and 'AND' in line.upper():
                break
            seen.add(normalized)
            clean_lines.append(line)
        sql = '\n'.join(clean_lines).strip()
        sql = re.sub(r'COUNT\([A-Za-z_]+\)', 'COUNT(*)', sql, flags=re.IGNORECASE)

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
    print("Starting Anand Rathi MCP Server (v3.1 - Dynamic Prompt)...", file=sys.stderr)
    print("Tools: connect_database, get_schema, execute_query, generate_sql", file=sys.stderr)
    mcp.run()