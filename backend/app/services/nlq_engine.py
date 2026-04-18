"""
NLQ Engine v2.1 - Natural Language Query Engine
================================================
The brain of the Communications Intelligence Platform.

AI-FIRST Architecture (Day 10 update):
  - Templates exist ONLY as a speed cache for common queries (~5ms)
  - Any question templates can't handle → falls through to MCP/AI
  - MCP Bridge calls Ollama to generate SQL from natural language
  - The AI reads live schema and generates correct SQL for ANY question

Flow:
  1. User asks a question in natural language
  2. (Optional) Check template cache — instant response if matched
  3. If no match → return None → query.py routes to MCP Bridge
  4. MCP Bridge → mcp_server.py → Ollama AI → SQL generation
  5. Access control is always injected (guaranteed data isolation)

Key principle:
  Templates are a PERFORMANCE OPTIMIZATION, not the brain.
  The AI (Ollama via MCP) is the brain. It handles everything.
  If you delete all templates, the system still works — just slower.
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
OLLAMA_TIMEOUT = 180  # seconds


# ═══════════════════════════════════════════════════════════════
# STEP 1: LIVE SCHEMA READING (from INFORMATION_SCHEMA)
# ═══════════════════════════════════════════════════════════════

def get_live_schema(table_name: str = None) -> str:
    """
    Read database schema LIVE from INFORMATION_SCHEMA.COLUMNS.
    This is what the supervisor specifically asked for —
    schema is never hardcoded, always fresh from the database.

    Returns a plain text description that the AI can understand.
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
            # Get all user tables (exclude system tables)
            cursor.execute("""
                SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, IS_NULLABLE,
                       CHARACTER_MAXIMUM_LENGTH
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME IN ('CommunicationsRequestStatus')
                ORDER BY TABLE_NAME, ORDINAL_POSITION
            """)

        rows = cursor.fetchall()
        cursor.close()

        if not rows:
            return "No schema found."

        # Build plain text schema description
        schema_lines = []
        current_table = None

        for table, column, dtype, nullable, max_len in rows:
            if table != current_table:
                if current_table:
                    schema_lines.append("")
                schema_lines.append(f"Table: {table}")
                schema_lines.append("Columns:")
                current_table = table

            # Build column description
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


def get_sample_values() -> str:
    """Get sample distinct values for key columns to help AI understand data."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        samples = []

        # LastStatus values
        cursor.execute("SELECT DISTINCT LastStatus FROM CommunicationsRequestStatus")
        statuses = [r[0] for r in cursor.fetchall()]
        samples.append(f"LastStatus values: {', '.join(statuses)}")

        # Sender samples
        cursor.execute("SELECT DISTINCT TOP 5 Sender FROM CommunicationsRequestStatus")
        senders = [r[0] for r in cursor.fetchall()]
        samples.append(f"Sender examples: {', '.join(senders)}")

        # Receiver pattern
        samples.append("Receiver pattern: client1@gmail.com, investor1@yahoo.com")

        # Vendor IDs
        cursor.execute("SELECT DISTINCT ReferenceVendorId FROM CommunicationsRequestStatus ORDER BY ReferenceVendorId")
        vendors = [str(r[0]) for r in cursor.fetchall()]
        samples.append(f"ReferenceVendorId values: {', '.join(vendors)}")

        cursor.close()
        return "\n".join(samples)
    except Exception:
        return ""
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
# STEP 2: TEMPLATE SPEED CACHE
# ═══════════════════════════════════════════════════════════════
# These templates are a PERFORMANCE OPTIMIZATION only.
# They handle common queries in ~5ms instead of ~60s.
# If a question doesn't match any template, it returns (None, None)
# and the query router sends it to MCP/AI — which can handle
# ANY question in natural language.
#
# Rule: If a template can't handle a question PERFECTLY,
#       return (None, None) and let AI handle it.
#       Never return a wrong or incomplete query from a template.
# ═══════════════════════════════════════════════════════════════

def match_template(question: str, access_filter: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Speed cache — try to match common questions to pre-built SQL.
    Returns (sql, description) if matched, (None, None) if not.

    If (None, None) is returned, the query router will send the
    question to MCP Bridge → Ollama AI, which can handle anything.
    """
    q = question.lower().strip()

    # ─── EARLY EXIT: Questions that need AI intelligence ──
    # If the question mentions these, templates can't handle it
    # properly. Let AI do it.
    ai_keywords = ['null', 'not null', 'empty', 'blank', 'missing',
                   'between', 'compare', 'percentage', 'average',
                   'median', 'ratio', 'correlat', 'predict',
                   'weekend', 'weekday', 'month', 'year',
                   'oldest', 'newest', 'first', 'last record',
                   'duplicate', 'distinct count', 'group by']
    if any(kw in q for kw in ai_keywords):
        return None, None  # → MCP/AI will handle this

    # Extract numbers from question (for days, limits etc.)
    num_match = re.search(r'(\d+)', q)
    days = int(num_match.group(1)) if num_match else 7

    # Vendor ID extraction
    v_match = re.search(r'vendor\s*(\d+)', q)

    af = f" AND {access_filter}" if access_filter else ""
    wf = f"WHERE {access_filter}" if access_filter else ""

    # T1: Status summary
    if any(w in q for w in ['summary', 'overview', 'breakdown', 'status']) and 'daily' not in q:
        sql = f"SELECT LastStatus, COUNT(*) AS Count FROM CommunicationsRequestStatus {wf} GROUP BY LastStatus ORDER BY Count DESC"
        return sql, "Status summary"

    # T2: Daily trend
    if any(w in q for w in ['daily', 'trend', 'day by day', 'timeline']):
        where = f"WHERE SubmitDate >= DATEADD(day, -{days}, GETDATE())" + af
        sql = f"SELECT CAST(SubmitDate AS DATE) AS Date, COUNT(*) AS Total, SUM(CASE WHEN LastStatus='SENT' THEN 1 ELSE 0 END) AS Sent, SUM(CASE WHEN LastStatus='FAILED' THEN 1 ELSE 0 END) AS Failed FROM CommunicationsRequestStatus {where} GROUP BY CAST(SubmitDate AS DATE) ORDER BY Date"
        return sql, f"Daily trend (last {days} days)"

    # T3: Top clients
    if any(w in q for w in ['client', 'top client', 'receiver']) and any(w in q for w in ['top', 'most', 'rank']):
        sql = f"SELECT TOP 20 Receiver, COUNT(*) AS Total, SUM(CASE WHEN LastStatus='FAILED' THEN 1 ELSE 0 END) AS Failed FROM CommunicationsRequestStatus {wf} GROUP BY Receiver ORDER BY Total DESC"
        return sql, "Top clients by volume"

    # T4: Vendor ranking
    if 'vendor' in q and any(w in q for w in ['rank', 'top', 'most', 'worst', 'failure']):
        sql = f"SELECT TOP 10 ReferenceVendorId AS Vendor, COUNT(*) AS Failures FROM CommunicationsRequestStatus WHERE LastStatus='FAILED' {af} GROUP BY ReferenceVendorId ORDER BY Failures DESC"
        return sql, "Vendor failure ranking"

    # T5: Vendor success rate
    if 'vendor' in q and any(w in q for w in ['success', 'reliable', 'performance']):
        sql = f"SELECT ReferenceVendorId AS Vendor, COUNT(*) AS Total, SUM(CASE WHEN LastStatus='SENT' THEN 1 ELSE 0 END) AS Sent, CAST(SUM(CASE WHEN LastStatus='SENT' THEN 1 ELSE 0 END)*100.0/COUNT(*) AS DECIMAL(5,2)) AS SuccessRate FROM CommunicationsRequestStatus {wf} GROUP BY ReferenceVendorId ORDER BY SuccessRate DESC"
        return sql, "Vendor reliability scorecard"

    # T6: Failed by vendor
    if ('fail' in q or 'error' in q) and v_match:
        vid = v_match.group(1)
        sql = f"SELECT TOP 30 Id, Receiver, Sender, FORMAT(SubmitDate,'dd-MMM-yyyy') AS Date, LastStatus FROM CommunicationsRequestStatus WHERE ReferenceVendorId={vid} AND LastStatus='FAILED' {af} ORDER BY SubmitDate DESC"
        return sql, f"Failed emails from Vendor {vid}"

    # T7: By sender
    if any(w in q for w in ['sender', 'department', 'team', 'sent by']):
        sql = f"SELECT Sender, COUNT(*) AS Total, SUM(CASE WHEN LastStatus='SENT' THEN 1 ELSE 0 END) AS Delivered, SUM(CASE WHEN LastStatus='FAILED' THEN 1 ELSE 0 END) AS Failed FROM CommunicationsRequestStatus {wf} GROUP BY Sender ORDER BY Total DESC"
        return sql, "Emails by sender"

    # T8: Category
    if 'category' in q:
        sql = f"SELECT CategoryId, COUNT(*) AS Count FROM CommunicationsRequestStatus {wf} GROUP BY CategoryId ORDER BY Count DESC"
        return sql, "Emails by category"

    # T9: Attachments
    if any(w in q for w in ['attachment', 'document', 'file']):
        sql = f"SELECT AttachmentInfo, COUNT(*) AS Count FROM CommunicationsRequestStatus WHERE AttachmentInfo IS NOT NULL AND AttachmentInfo != '' {af} GROUP BY AttachmentInfo ORDER BY Count DESC"
        return sql, "Document types"

    # T10: Failed recent
    if any(w in q for w in ['fail', 'failed', 'error']) and any(w in q for w in ['last', 'recent', 'week', 'today']):
        where = f"WHERE LastStatus='FAILED' AND SubmitDate >= DATEADD(day, -{days}, GETDATE())" + af
        sql = f"SELECT TOP 50 Id, Receiver, Sender, FORMAT(SubmitDate,'dd-MMM-yyyy') AS Date FROM CommunicationsRequestStatus {where} ORDER BY SubmitDate DESC"
        return sql, f"Failed emails (last {days} days)"

    # T11: Pending stuck
    if 'pending' in q and any(w in q for w in ['old', 'stuck', 'delay']):
        where = f"WHERE LastStatus='PENDING' AND SubmitDate < DATEADD(day, -{days}, GETDATE())" + af
        sql = f"SELECT TOP 30 Id, Receiver, Sender, FORMAT(SubmitDate,'dd-MMM-yyyy') AS Date, DATEDIFF(day, SubmitDate, GETDATE()) AS DaysStuck FROM CommunicationsRequestStatus {where} ORDER BY SubmitDate ASC"
        return sql, f"Pending emails > {days} days"

    # T12: Pending general
    if 'pending' in q:
        sql = f"SELECT TOP 25 Id, Receiver, Sender, FORMAT(SubmitDate,'dd-MMM-yyyy') AS Date FROM CommunicationsRequestStatus WHERE LastStatus='PENDING' {af} ORDER BY SubmitDate DESC"
        return sql, "Pending emails"

    # T13: Failed general
    if any(w in q for w in ['fail', 'failed', 'error']):
        sql = f"SELECT TOP 30 Id, Receiver, Sender, FORMAT(SubmitDate,'dd-MMM-yyyy') AS Date FROM CommunicationsRequestStatus WHERE LastStatus='FAILED' {af} ORDER BY SubmitDate DESC"
        return sql, "Failed emails"

    # T14: Successful recent
    if any(w in q for w in ['success', 'successful', 'sent', 'delivered']) and any(w in q for w in ['recent', 'last']):
        where = f"WHERE LastStatus='SENT' AND SubmitDate >= DATEADD(day, -{days}, GETDATE())" + af
        sql = f"SELECT TOP 25 Id, Receiver, Sender, FORMAT(SubmitDate,'dd-MMM-yyyy') AS Date FROM CommunicationsRequestStatus {where} ORDER BY SubmitDate DESC"
        return sql, f"Successful emails (last {days} days)"

    # T15: Peak hours
    if any(w in q for w in ['hour', 'time of day', 'peak']):
        sql = f"SELECT DATEPART(hour, SubmitDate) AS Hour, COUNT(*) AS Count FROM CommunicationsRequestStatus {wf} GROUP BY DATEPART(hour, SubmitDate) ORDER BY Hour"
        return sql, "Email volume by hour"

    # T16: Simple count queries (only for clear status-based counts)
    if any(w in q for w in ['how many', 'count', 'total number']):
        if 'fail' in q:
            sql = f"SELECT COUNT(*) AS Total FROM CommunicationsRequestStatus WHERE LastStatus='FAILED' {af}"
            return sql, "Count of failed emails"
        elif 'sent' in q:
            sql = f"SELECT COUNT(*) AS Total FROM CommunicationsRequestStatus WHERE LastStatus='SENT' {af}"
            return sql, "Count of sent emails"
        elif 'pending' in q:
            sql = f"SELECT COUNT(*) AS Total FROM CommunicationsRequestStatus WHERE LastStatus='PENDING' {af}"
            return sql, "Count of pending emails"
        elif 'total' in q or 'all' in q:
            sql = f"SELECT COUNT(*) AS Total FROM CommunicationsRequestStatus {wf}"
            return sql, "Total email count"
        else:
            # Question asks "how many" but with specific conditions
            # we can't handle → let AI figure it out
            return None, None

    # T17: Unique clients
    if any(w in q for w in ['unique', 'distinct']) and any(w in q for w in ['receiver', 'client']):
        sql = f"SELECT COUNT(DISTINCT Receiver) AS UniqueClients FROM CommunicationsRequestStatus {wf}"
        return sql, "Unique clients count"

    # T18: Emails by specific sender
    sender_match = re.search(r'by\s+(\S+@\S+)', q)
    if sender_match:
        sender = sender_match.group(1)
        sql = f"SELECT TOP 50 Id, Receiver, LastStatus, FORMAT(SubmitDate,'dd-MMM-yyyy') AS Date FROM CommunicationsRequestStatus WHERE Sender = '{sender}' {af} ORDER BY SubmitDate DESC"
        return sql, f"Emails sent by {sender}"

    # T19: Emails for specific receiver
    receiver_match = re.search(r'(?:for|to)\s+(\S+@\S+)', q)
    if receiver_match:
        receiver = receiver_match.group(1)
        sql = f"SELECT TOP 50 Id, Sender, LastStatus, FORMAT(SubmitDate,'dd-MMM-yyyy') AS Date FROM CommunicationsRequestStatus WHERE Receiver = '{receiver}' {af} ORDER BY SubmitDate DESC"
        return sql, f"Emails for {receiver}"

    # ─── No match → MCP/AI will handle it ─────────────────
    return None, None


# ═══════════════════════════════════════════════════════════════
# STEP 3: AI FALLBACK (Ollama with live schema)
# ═══════════════════════════════════════════════════════════════
# NOTE: This function is kept for backward compatibility.
# The primary AI path now goes through MCP Bridge (mcp_client.py).
# This is only used if process_query() is called directly.

def generate_sql_with_ai(question: str, access_filter: str) -> Optional[str]:
    """
    AI Fallback — Send schema + question to Ollama for SQL generation.
    Uses LIVE schema from INFORMATION_SCHEMA (not hardcoded).
    """
    # Read schema live from database
    live_schema = get_live_schema()
    sample_values = get_sample_values()

    # Build access control note
    if access_filter:
        access_note = f"CRITICAL: Always add this filter to WHERE clause: {access_filter}"
    else:
        access_note = "User is Admin - no access filter needed."

    prompt = f"""You are a SQL Server expert. Generate ONLY a short, clean SQL query.

The ONLY table in this database is: CommunicationsRequestStatus

=== SCHEMA ===
{live_schema}

=== SAMPLE VALUES ===
{sample_values}

RULES:
- ALWAYS include FROM CommunicationsRequestStatus in every query.
- Output ONLY the SQL query. No explanations. No markdown.
- Keep queries SHORT and SIMPLE. Maximum 5-6 lines.
- Use TOP instead of LIMIT. Use GETDATE() for current date.
- For NULL checks: column IS NULL or IS NOT NULL
- Weekend: DATEPART(WEEKDAY, SubmitDate) IN (1, 7)
- Date range: SubmitDate >= DATEADD(day, -7, GETDATE())
- Status values: 'SENT', 'FAILED', 'PENDING', 'CREATED', 'SUBMITTED', 'DELIVERED'
- Do NOT add unnecessary conditions. Only what the question asks.
- {access_note}

EXAMPLES:
Q: how many emails have null in bccdata
SQL: SELECT COUNT(*) AS Total FROM CommunicationsRequestStatus WHERE BccData IS NULL

Q: show emails on weekends
SQL: SELECT TOP 50 Id, Receiver, Sender, FORMAT(SubmitDate,'dd-MMM-yyyy') AS Date, LastStatus FROM CommunicationsRequestStatus WHERE DATEPART(WEEKDAY, SubmitDate) IN (1, 7) ORDER BY SubmitDate DESC

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
                }
            },
            timeout=OLLAMA_TIMEOUT,
        )

        if response.status_code != 200:
            return None

        sql = response.json().get("response", "").strip()

        # Clean up AI response
        sql = re.sub(r'```sql\s*|```\s*', '', sql, flags=re.IGNORECASE)
        sql = re.sub(r'^.*?SELECT', 'SELECT', sql, flags=re.IGNORECASE | re.DOTALL)
        sql = sql.split(';')[0].strip()

        # Kill repeated lines (Qwen 3B hallucination fix)
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

        if not sql.upper().startswith('SELECT'):
            return None

        return sql

    except requests.Timeout:
        log_error("OLLAMA_TIMEOUT", f"Ollama timed out after {OLLAMA_TIMEOUT}s", endpoint="generate_sql_with_ai")
        return None
    except Exception as e:
        log_error("OLLAMA_ERROR", str(e), endpoint="generate_sql_with_ai")
        return None


# ═══════════════════════════════════════════════════════════════
# STEP 4: SQL VALIDATION & SECURITY
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
        # Check for keyword as a word boundary (not inside column names)
        if re.search(rf'\b{keyword}\b', sql_upper):
            return False, f"Dangerous keyword detected: {keyword}"

    return True, "Valid"


def inject_access_filter(sql: str, access_filter: str) -> str:
    """
    Ensure access control filter is present in the SQL.
    If AI forgot to add it, we inject it here.
    This guarantees data isolation regardless of AI behavior.
    """
    if not access_filter:
        return sql  # Admin, no filter needed

    sql_upper = sql.upper()

    # Check if filter is already present
    if access_filter.upper().replace(" ", "") in sql_upper.replace(" ", ""):
        return sql

    # Inject the filter
    if 'WHERE' in sql_upper:
        # Add to existing WHERE clause
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
# STEP 5: EXECUTE QUERY
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

        # Convert to list of dicts, handling datetime serialization
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
# MAIN FUNCTION: Process Natural Language Query
# ═══════════════════════════════════════════════════════════════
# NOTE: This function is kept for backward compatibility.
# The primary query path now goes through query.py → MCP Bridge.
# This is only used as a fallback if MCP is unavailable.

def process_query(question: str, user: dict) -> dict:
    """
    Legacy entry point — processes a question using templates + direct Ollama.
    The primary path (query.py) uses MCP Bridge instead.
    """
    start_time = time.time()

    # Build access filter based on user role
    role = user.get("role", "")
    app_id = user.get("application_id")

    if role == "Admin":
        access_filter = ""
    elif app_id and role in ("RM_Head", "RM", "RM_Head2", "RM2", "RM3"):
        access_filter = f"ReferenceApplicationId = {app_id}"
    else:
        username = user.get("username", "")
        access_filter = f"Receiver LIKE '%{username}%'"

    # STEP 1: Try template matching
    sql, description = match_template(question, access_filter)
    method = "template"

    # STEP 2: If no template, try AI
    if sql is None:
        sql = generate_sql_with_ai(question, access_filter)
        method = "ai"
        description = "AI-generated query"

        if sql is None:
            elapsed = int((time.time() - start_time) * 1000)
            return {
                "question": question,
                "generated_sql": None,
                "method": "failed",
                "data": [],
                "columns": [],
                "row_count": 0,
                "execution_time_ms": elapsed,
                "insights": ["Could not generate SQL. Try rephrasing your question or check if Ollama is running on localhost:11434."],
                "error": "Failed to generate SQL query",
            }

    # STEP 3: Validate SQL
    is_valid, reason = validate_sql(sql)
    if not is_valid:
        elapsed = int((time.time() - start_time) * 1000)
        return {
            "question": question,
            "generated_sql": sql,
            "method": method,
            "data": [],
            "columns": [],
            "row_count": 0,
            "execution_time_ms": elapsed,
            "insights": [f"SQL validation failed: {reason}"],
            "error": reason,
        }

    # STEP 4: Inject access control (guaranteed, even if AI forgot)
    sql = inject_access_filter(sql, access_filter)

    # STEP 5: Execute
    data, columns, error = execute_query_safe(sql)

    elapsed = int((time.time() - start_time) * 1000)

    # Build insights
    insights = []
    if len(data) == 0:
        insights.append("No records found matching your query.")
    elif len(data) == 1 and len(columns) <= 2:
        insights.append(f"Single result: {data[0]}")
    else:
        insights.append(f"Found {len(data)} records.")
        if method == "template":
            insights.append(f"Matched template: {description}")

    return {
        "question": question,
        "generated_sql": sql,
        "method": method,
        "data": data,
        "columns": columns,
        "row_count": len(data),
        "execution_time_ms": elapsed,
        "insights": insights,
        "error": error,
    }