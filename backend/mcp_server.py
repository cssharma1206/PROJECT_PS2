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
import os
import json
import re
import pyodbc
import requests
from mcp.server.fastmcp import FastMCP

# Try to import psycopg2 — only needed if a Postgres DB is configured
try:
    import psycopg2
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False


# ═══════════════════════════════════════════════════════════════
# CREATE MCP SERVER
# ═══════════════════════════════════════════════════════════════

mcp = FastMCP("anand-rathi-db")

# ═══════════════════════════════════════════════════════════════
# LOAD CONFIG FROM db_config.json
# ═══════════════════════════════════════════════════════════════

CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "db_config.json"
)


def _load_config() -> dict:
    """Load the database configuration from db_config.json."""
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"WARNING: Could not load db_config.json: {e}", file=sys.stderr)
        return {"default_database": "anandrathi", "databases": {}}


CONFIG = _load_config()
DEFAULT_DB_NAME = CONFIG.get("default_database", "anandrathi")

# ACTIVE_DB holds the current database name being queried.
# It's updated by the connect_database tool.
ACTIVE_DB = DEFAULT_DB_NAME


def _get_db_config(db_name: str = None) -> dict:
    """Get config block for a database name. Falls back to default."""
    name = db_name or ACTIVE_DB
    return CONFIG.get("databases", {}).get(name, {})

def _get_db_type(db_name: str = None) -> str:
    """Return 'sqlserver' or 'postgres' for the given db (or active)."""
    return _get_db_config(db_name).get("db_type", "sqlserver")


OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "gemma3:4b"
OLLAMA_TIMEOUT = 180


def _get_connection(db_name: str = None):
    """
    Create a database connection based on db_type in config.
    Supports: sqlserver (pyodbc), postgres (psycopg2).
    """
    cfg = _get_db_config(db_name)
    if not cfg:
        raise RuntimeError(f"No config found for database '{db_name or ACTIVE_DB}'")

    db_type = cfg.get("db_type", "sqlserver")

    if db_type == "sqlserver":
        return pyodbc.connect(
            f"DRIVER={cfg['driver']};"
            f"SERVER={cfg['server']};"
            f"DATABASE={cfg['database']};"
            f"Trusted_Connection={cfg.get('trusted_connection', 'yes')};"
        )
    elif db_type == "postgres":
        if not PSYCOPG2_AVAILABLE:
            raise RuntimeError(
                "psycopg2 not installed. Run: pip install psycopg2-binary"
            )
        return psycopg2.connect(
            host=cfg["host"],
            port=cfg.get("port", 5432),
            database=cfg["database"],
            user=cfg["username"],
            password=cfg["password"],
        )
    else:
        raise RuntimeError(f"Unsupported db_type: '{db_type}'")


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
def connect_database(database_name: str = "") -> str:
    """
    Switch the active database by name (as defined in db_config.json).

    Args:
        database_name: Database name from config, e.g. 'anandrathi' or 'anandrathi_trading'
    """
    global ACTIVE_DB
    name = database_name or DEFAULT_DB_NAME

    cfg = CONFIG.get("databases", {}).get(name)
    if not cfg:
        return f"Connection FAILED: Database '{name}' not found in config"

    try:
        conn = _get_connection(name)
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        ACTIVE_DB = name
        return f"Connected successfully to {name} ({cfg.get('db_type', 'sqlserver')})"
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
def execute_query(sql: str, max_rows: int = 50) -> str:
    """
    Execute a SQL SELECT query and return results.
    Only SELECT queries are allowed.

    Args:
        sql: The SQL SELECT query to execute
        max_rows: Max rows to return (default 50 for UI preview, raise for CSV export)
    """
    is_safe, reason = _validate_sql(sql)
    if not is_safe:
        return json.dumps({"status": "blocked", "error": reason})

    try:
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute(sql)

        if cursor.description is None:
            cursor.close()
            conn.close()
            return json.dumps({"status": "ok", "columns": [], "rows": [], "total": 0, "truncated": False})

        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        PREVIEW_CAP = max_rows
        total_rows = len(rows)
        preview_rows = []
        for row in rows[:PREVIEW_CAP]:
            row_data = {}
            for j, val in enumerate(row):
                if hasattr(val, 'isoformat'):
                    row_data[columns[j]] = val.isoformat()
                else:
                    row_data[columns[j]] = val
            preview_rows.append(row_data)

        return json.dumps({
            "status": "ok",
            "columns": columns,
            "rows": preview_rows,
            "total": total_rows,
            "truncated": total_rows > PREVIEW_CAP,
        }, default=str)

    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)})


# ═══════════════════════════════════════════════════════════════
# DYNAMIC PROMPT BUILDER (optimized v3.1)
# ═══════════════════════════════════════════════════════════════

# Columns to skip when sampling (they have long/noisy values)
SKIP_SAMPLE_COLUMNS = {'RequestData', 'Body', 'Subject', 'Gu_id',
                       'TrackingId', 'Password', 'PasswordHash'}

def _get_foreign_keys(table_names: list) -> list:
    """
    Read foreign key relationships for a list of tables.
    Returns list of dicts: [{from_table, from_column, to_table, to_column}, ...]
    Dialect-aware: SQL Server uses INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS,
    Postgres uses pg_catalog.
    """
    if not table_names:
        return []

    db_type = _get_db_type()
    fks = []

    try:
        conn = _get_connection()
        cursor = conn.cursor()

        if db_type == "sqlserver":
            placeholders = ",".join(["?"] * len(table_names))
            cursor.execute(f"""
                SELECT
                    fk_tab.TABLE_NAME AS from_table,
                    fk_col.COLUMN_NAME AS from_column,
                    pk_tab.TABLE_NAME AS to_table,
                    pk_col.COLUMN_NAME AS to_column
                FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc
                JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE fk_col
                    ON rc.CONSTRAINT_NAME = fk_col.CONSTRAINT_NAME
                JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS fk_tab
                    ON rc.CONSTRAINT_NAME = fk_tab.CONSTRAINT_NAME
                JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE pk_col
                    ON rc.UNIQUE_CONSTRAINT_NAME = pk_col.CONSTRAINT_NAME
                    AND fk_col.ORDINAL_POSITION = pk_col.ORDINAL_POSITION
                JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS pk_tab
                    ON rc.UNIQUE_CONSTRAINT_NAME = pk_tab.CONSTRAINT_NAME
                WHERE fk_tab.TABLE_NAME IN ({placeholders})
                  AND pk_tab.TABLE_NAME IN ({placeholders})
            """, tuple(table_names) + tuple(table_names))
        else:  # postgres
            placeholders = ",".join(["%s"] * len(table_names))
            cursor.execute(f"""
                SELECT
                    tc.table_name AS from_table,
                    kcu.column_name AS from_column,
                    ccu.table_name AS to_table,
                    ccu.column_name AS to_column
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                JOIN information_schema.constraint_column_usage ccu
                    ON tc.constraint_name = ccu.constraint_name
                WHERE tc.constraint_type = 'FOREIGN KEY'
                  AND tc.table_name IN ({placeholders})
                  AND ccu.table_name IN ({placeholders})
            """, tuple(table_names) + tuple(table_names))

        for row in cursor.fetchall():
            fks.append({
                "from_table": row[0],
                "from_column": row[1],
                "to_table": row[2],
                "to_column": row[3],
            })

        cursor.close()
        conn.close()
    except Exception as e:
        print(f"FK read error: {e}", file=sys.stderr)
        return []

    return fks

def _get_table_names() -> list:
    """Get all user table names from the connected database."""
    db_type = _get_db_type()
    schema_name = "public" if db_type == "postgres" else "dbo"

    try:
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT TABLE_NAME
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_TYPE = 'BASE TABLE'
              AND TABLE_SCHEMA = %s
              AND TABLE_NAME NOT IN ('sysdiagrams')
            ORDER BY TABLE_NAME
        """ if db_type == "postgres" else """
            SELECT TABLE_NAME
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_TYPE = 'BASE TABLE'
              AND TABLE_SCHEMA = ?
              AND TABLE_NAME NOT IN ('sysdiagrams')
            ORDER BY TABLE_NAME
        """, (schema_name,))
        tables = [r[0] for r in cursor.fetchall()]
        cursor.close()
        conn.close()
        return tables
    except Exception:
        return []


def _get_schema_and_samples(table_name: str) -> tuple:
    """
    Get columns AND sample values in ONE database connection.
    Works for both SQL Server and Postgres.
    Returns (columns_list, samples_dict, total_rows).
    """
    columns = []
    samples = {}
    total_rows = 0

    db_type = _get_db_type()
    is_postgres = (db_type == "postgres")

    # Identifier quoting: SQL Server uses [name], Postgres uses "name"
    ql, qr = ('"', '"') if is_postgres else ('[', ']')
    # Parameter placeholder
    ph = "%s" if is_postgres else "?"
    # Row-limit syntax
    def limit_clause(n):
        return f"LIMIT {n}" if is_postgres else f"TOP {n}"
    # String-type names per dialect
    string_types = ('character varying', 'text', 'varchar') if is_postgres \
                   else ('nvarchar', 'varchar')
    int_types = ('integer', 'smallint', 'bigint') if is_postgres \
                else ('int', 'smallint', 'tinyint')

    try:
        conn = _get_connection()
        cursor = conn.cursor()

        # Get columns
        cursor.execute(f"""
            SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = {ph}
            ORDER BY ORDINAL_POSITION
        """, (table_name,))
        columns = [(r[0], r[1], r[2]) for r in cursor.fetchall()]

        # Get total rows
        cursor.execute(f"SELECT COUNT(*) FROM {ql}{table_name}{qr}")
        total_rows = cursor.fetchone()[0]

        # Sample useful columns
        for col_name, col_type, _ in columns:
            if col_name in SKIP_SAMPLE_COLUMNS:
                continue

            if col_type not in string_types and col_type not in int_types:
                continue

            try:
                if is_postgres:
                    sql = f"""
                        SELECT DISTINCT {ql}{col_name}{qr}
                        FROM {ql}{table_name}{qr}
                        WHERE {ql}{col_name}{qr} IS NOT NULL
                          AND CAST({ql}{col_name}{qr} AS TEXT) != ''
                          AND LENGTH(CAST({ql}{col_name}{qr} AS TEXT)) < 50
                        ORDER BY {ql}{col_name}{qr}
                        LIMIT 10
                    """
                else:
                    sql = f"""
                        SELECT DISTINCT TOP 10 {ql}{col_name}{qr}
                        FROM {ql}{table_name}{qr}
                        WHERE {ql}{col_name}{qr} IS NOT NULL AND CAST({ql}{col_name}{qr} AS NVARCHAR(100)) != ''
                          AND LEN(CAST({ql}{col_name}{qr} AS NVARCHAR(MAX))) < 50
                        ORDER BY {ql}{col_name}{qr}
                    """
                cursor.execute(sql)
                values = [str(r[0]).strip() for r in cursor.fetchall()]
                if values and len(values) <= 10:
                    samples[col_name] = values
            except Exception:
                continue

        cursor.close()
        conn.close()
    except Exception:
        pass

    return columns, samples, total_rows

def _get_multi_table_schema(table_names: list) -> dict:
    """
    Get column info and sample values for multiple tables.
    Returns {table_name: {"columns": [...], "samples": {...}, "rows": N}}
    """
    result = {}
    for t in table_names:
        cols, samples, total = _get_schema_and_samples(t)
        if cols:
            result[t] = {"columns": cols, "samples": samples, "rows": total}
    return result

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

    # Dialect-aware syntax hints
    db_type = _get_db_type()
    if db_type == "postgres":
        syntax_rule = "- PostgreSQL syntax: LIMIT N (not TOP), NOW() (not GETDATE()), use double quotes \"column\" for identifiers. Column names are lowercase."
    else:
        syntax_rule = "- SQL Server syntax: TOP (not LIMIT), GETDATE(), DATEADD(), DATEPART()"

    # Build rules
    rules = [
        f"- Table: {table_name}",
        f"- ALWAYS use FROM {table_name}",
        "- Output ONLY SQL. No text. No markdown. No backticks.",
        syntax_rule,
        f"- EXACT column names: {', '.join(col_names)}",
        "- NEVER invent column names. ONLY use columns listed above.",
        "- For counting rows, ALWAYS use COUNT(*), NEVER use COUNT(column_name) — COUNT(column) skips NULLs.",
    ]

    if date_cols:
        dc = date_cols[0]
        if db_type == "postgres":
            rules.append(f"- Date column: {dc}. Use TO_CHAR({dc}, 'DD-Mon-YYYY') for display.")
            rules.append(f"- Date range: {dc} >= NOW() - INTERVAL '7 days'")
            rules.append(f"- Weekends: EXTRACT(DOW FROM {dc}) IN (0, 6)")
        else:
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

    # Build 4-5 concise examples
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


def _build_multi_table_prompt(question: str, table_names: list, category_name: str = "") -> str:
    """
    Build an AI prompt for a category (multiple related tables with FK relationships).
    The AI is told which tables exist, their columns, and how they JOIN.
    It decides whether to query one table or JOIN multiple based on the question.
    """
    if not table_names:
        return None

    # Read schema for all category tables
    schemas = _get_multi_table_schema(table_names)
    if not schemas:
        return None

    # Read FK relationships between these tables
    fks = _get_foreign_keys(table_names)

    db_type = _get_db_type()

    # Build table descriptions
    table_blocks = []
    for tname, info in schemas.items():
        col_lines = [f"  - {c[0]} ({c[1]})" for c in info["columns"]]
        sample_lines = []
        for col, vals in info["samples"].items():
            if vals:
                sample_lines.append(f"    {col}: {', '.join(vals[:5])}")
        sample_block = "\n".join(sample_lines) if sample_lines else "    (none)"

        table_blocks.append(
            f"TABLE: {tname} ({info['rows']} rows)\n"
            f"COLUMNS:\n" + "\n".join(col_lines) + "\n"
            f"SAMPLE VALUES:\n{sample_block}"
        )

    # Build FK relationship block
    if fks:
        fk_lines = [
            f"  - {fk['from_table']}.{fk['from_column']} = {fk['to_table']}.{fk['to_column']}"
            for fk in fks
        ]
        fk_block = "RELATIONSHIPS (use for JOINs when question needs data from multiple tables):\n" + "\n".join(fk_lines)
    else:
        fk_block = "RELATIONSHIPS: (none — tables are independent)"

    # Dialect-aware syntax
    if db_type == "postgres":
        syntax_rule = "- PostgreSQL syntax: LIMIT N (not TOP), NOW() (not GETDATE()), lowercase column names."
    else:
        syntax_rule = "- SQL Server syntax: TOP N (not LIMIT), GETDATE(), DATEADD()."

    # Rules
    rules = [
        f"- Category: {category_name or 'multi-table'}",
        f"- Tables available: {', '.join(schemas.keys())}",
        "- Output ONLY SQL. No text. No markdown. No backticks.",
        syntax_rule,
        "- DEFAULT TO ONE TABLE. Only use JOIN if the question explicitly asks for columns from a second table or asks to combine data across tables.",
        "- DO NOT JOIN just because a foreign key exists. Foreign keys are listed for reference, not as instructions to join.",
        "- WARNING: INNER JOIN with CommunicationErrorMaster will DROP ALL SUCCESS rows because errors only exist for failed messages. Never INNER JOIN error tables for questions about Status counts, ServiceType counts, or general message statistics — these need only CommunicationMaster.",
        "- For questions like 'count by status', 'count by service type', 'how many messages', 'count of communications', or 'message distribution' — use ONLY CommunicationMaster. No JOIN.",
        "- Only JOIN CommunicationErrorMaster when the question explicitly mentions errors, error types, error summaries, or asks to combine messages with their failure reasons.",
        "- Only JOIN ApplicationMaster when the question asks for ApplicationName or ApplicationCode (not just ApplicationId).",
        "- JOIN ALIAS RULE: each table must get a UNIQUE alias using first-letter-of-each-word. Example: CommunicationMaster→cm, CommunicationErrorMaster→cem, ApplicationMaster→am. NEVER use the same alias for two tables.",
        "- NEVER invent column names. Only use columns listed in the TABLE blocks.",
        "- For counting rows, use COUNT(*), NEVER COUNT(column_name).",
        "- NEVER use TOP/LIMIT when the query has GROUP BY — GROUP BY may produce multiple rows and TOP truncates them.",
        "- When grouping, ALWAYS include the grouping column in SELECT so results are readable (e.g., SELECT am.ApplicationName, COUNT(*) FROM ...).",
        "- Only use TOP N for listing/ranking queries without GROUP BY, like 'show top 10 recipients'.",
        "- CRITICAL: Status values like SUCCESS, FAILED, BOUNCE, DROPPED, DUPLICATE are columns in CommunicationMaster, NOT errors. Questions about message Status (including bounced, dropped, duplicate, failed messages) need ONLY CommunicationMaster. Do NOT JOIN CommunicationErrorMaster for Status questions.",
        "- CommunicationErrorMaster contains ONLY rows where Status = 'FAILED'. It does NOT contain rows for BOUNCE, DROPPED, or DUPLICATE messages. JOINing with it for non-FAILED status questions returns ZERO rows.",
    ]

    # Choose a default anchor table for examples
    anchor = next((t for t in schemas.keys() if "Master" in t and "Error" not in t), list(schemas.keys())[0])
    anchor_cols = [c[0] for c in schemas[anchor]["columns"]]
    top5 = ", ".join(anchor_cols[:5])

    # Dialect-aware top-N syntax for examples
    top_50 = "SELECT TOP 50" if db_type == "sqlserver" else "SELECT"
    limit_50 = "" if db_type == "sqlserver" else " LIMIT 50"

    # Build examples
    examples = ["EXAMPLES:"]

    # Example 1: single table
    examples.append(f"Q: show records from {anchor}")
    examples.append(f"SQL: {top_50} {top5} FROM {anchor}{limit_50}")
    examples.append("")

    # Example 2: JOIN using an FK (if any exist)
    if fks:
        fk0 = fks[0]
        fr, ft = fk0["from_table"], fk0["to_table"]
        fc, tc = fk0["from_column"], fk0["to_column"]
        def _alias(tname):
            return "".join(c.lower() for c in tname if c.isupper()) or tname[:2].lower()
        fr_alias = _alias(fr)
        ft_alias = _alias(ft)
        if fr_alias == ft_alias:
            ft_alias = ft_alias + "2"
        examples.append(f"Q: {fr} joined with {ft}")
        examples.append(
            f"SQL: {top_50} {fr_alias}.*, {ft_alias}.* FROM {fr} {fr_alias} "
            f"INNER JOIN {ft} {ft_alias} ON {fr_alias}.{fc} = {ft_alias}.{tc}{limit_50}"
        )
        
        # Example 3: GROUP BY aggregation (no TOP when grouping)
    if fks and db_type == "sqlserver":
        # Find a good grouping target: ApplicationMaster has ApplicationName we want
        am_table = next((t for t in schemas.keys() if "Application" in t and "Access" not in t and "Error" not in t), None)
        if am_table:
            am_alias = _alias(am_table)
            # Find the FK that connects to this ApplicationMaster
            fk_to_am = next((fk for fk in fks if fk["to_table"] == am_table), None)
            if fk_to_am:
                other_table = fk_to_am["from_table"]
                other_alias = _alias(other_table)
                if other_alias == am_alias:
                    other_alias = other_alias + "2"
                examples.append(f"Q: count per application")
                examples.append(
                    f"SQL: SELECT {am_alias}.ApplicationName, COUNT(*) AS Total "
                    f"FROM {other_table} {other_alias} "
                    f"INNER JOIN {am_table} {am_alias} ON {other_alias}.{fk_to_am['from_column']} = {am_alias}.{fk_to_am['to_column']} "
                    f"GROUP BY {am_alias}.ApplicationName"
                )
        examples.append("")
        

    # Assemble full prompt
    prompt = f"""You are a SQL query generator for a multi-table category. Output ONLY raw SQL.

{chr(10) + chr(10).join(table_blocks)}

{fk_block}

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
def generate_sql(
    question: str,
    schema_text: str = "",
    table_name: str = "",
    category_tables: str = "",
    category_name: str = "",
) -> str:

    """
    Generate a SQL query from a natural language question.

    Two modes:
      - Single-table (legacy): pass table_name, category_tables empty
      - Category (new): pass category_tables="tbl1,tbl2,tbl3", table_name empty

    Args:
        question: Natural language question
        schema_text: Optional. Kept for backward compat.
        table_name: Single-table mode: which table to query
        category_tables: Category mode: comma-separated list of tables
        category_name: Category mode: human-readable category name for prompt
    """
    # Category mode takes priority if provided
    if category_tables:
        tables = [t.strip() for t in category_tables.split(",") if t.strip()]
        prompt = _build_multi_table_prompt(question, tables, category_name)
    else:
        # Single-table mode (unchanged existing behavior)
        if table_name:
            target_table = table_name
        else:
            all_tables = _get_table_names()
            skip_tables = {'users', 'users_v2', 'roles', 'token',
                           'accesslog', 'sysdiagrams'}
            target_table = None
            for t in all_tables:
                if t.lower() not in skip_tables:
                    target_table = t
                    break
            if not target_table:
                target_table = all_tables[0] if all_tables else "CommunicationMaster"
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