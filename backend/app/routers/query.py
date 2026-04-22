"""
Query Router - /api/v1/query
=============================
AI-FIRST with database switching + table switching.

Endpoints:
  POST /api/v1/query           - Process a natural language question
  GET  /api/v1/query/databases - List available databases
  GET  /api/v1/query/tables    - List queryable tables for selected database
  GET  /api/v1/query/schema    - Get live database schema
"""

import time
from fastapi import APIRouter, Depends, HTTPException, Query as QueryParam
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from app.middleware.auth_middleware import get_current_user
from app.services.mcp_client import (
    mcp_bridge, get_available_databases, get_allowed_tables,
    get_default_table, DEFAULT_DATABASE, DATABASES,
)
from app.services.nlq_engine import get_live_schema
from app.services.database import execute_non_query
from app.services.error_logger import log_error

router = APIRouter(prefix="/api/v1/query", tags=["Query"])

# ═══════════════════════════════════════════════════════════════
# PYDANTIC MODELS
# ═══════════════════════════════════════════════════════════════

class QueryRequest(BaseModel):
    question: str
    table_name: Optional[str] = None
    database: Optional[str] = None
    category: Optional[str] = None


class QueryResponse(BaseModel):
    question: str
    generated_sql: Optional[str]
    method: str
    data: List[Dict[str, Any]]
    columns: List[str]
    row_count: int
    total_rows: int = 0
    truncated: bool = False
    execution_time_ms: int
    insights: List[str]
    error: Optional[str]


class SchemaResponse(BaseModel):
    schema_text: str


class DatabaseInfo(BaseModel):
    database: str
    label: str
    description: str


class DatabasesResponse(BaseModel):
    databases: List[DatabaseInfo]
    default: str


class TableInfo(BaseModel):
    table_name: str
    label: str
    description: str


class TablesResponse(BaseModel):
    tables: List[TableInfo]
    default: str


# ═══════════════════════════════════════════════════════════════
# GET /api/v1/query/databases — List available databases
# ═══════════════════════════════════════════════════════════════

@router.get("/databases", response_model=DatabasesResponse)
async def list_databases(user: dict = Depends(get_current_user)):
    """Returns all available databases the user can query."""
    dbs = get_available_databases()
    return DatabasesResponse(
        databases=[DatabaseInfo(**d) for d in dbs],
        default=DEFAULT_DATABASE,
    )


# ═══════════════════════════════════════════════════════════════
# GET /api/v1/query/tables — List tables for a database
# ═══════════════════════════════════════════════════════════════

@router.get("/tables", response_model=TablesResponse)
async def list_tables(
    database: str = QueryParam(default=None),
    user: dict = Depends(get_current_user),
):
    """Returns tables available in the selected database."""
    db = database or DEFAULT_DATABASE
    user_role = user.get("role", "")
    tables = get_allowed_tables(db, user_role)
    default_table = get_default_table(db)
    return TablesResponse(
        tables=[TableInfo(**t) for t in tables],
        default=default_table,
    )


# ═══════════════════════════════════════════════════════════════
# POST /api/v1/query — Main query endpoint
# ═══════════════════════════════════════════════════════════════

@router.post("", response_model=QueryResponse)
async def natural_language_query(
    request: QueryRequest,
    user: dict = Depends(get_current_user)
):
    """
    Process a natural language question.

    Request body:
        {
            "question": "show status summary",
            "database": "anandrathi",          // optional
            "table_name": "CommunicationsRequestStatus"  // optional
        }
    """
    question = request.question.strip()
    database = request.database or DEFAULT_DATABASE
    table_name = request.table_name or get_default_table(database)

    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    if len(question) < 3:
        raise HTTPException(status_code=400, detail="Question too short")
    if len(question) > 500:
        raise HTTPException(status_code=400, detail="Question too long (max 500 characters)")
    
    # Pre-Ollama safety filter: reject questions containing destructive intent
    # before we spend 140s generating SQL for something we'd reject anyway.
    DANGEROUS_INTENT_KEYWORDS = [
        'delete', 'drop', 'truncate', 'remove all',
        'erase', 'wipe', 'destroy', 'purge',
        'alter table', 'insert into', 'update set',
        'create table', 'grant', 'revoke',
    ]
    DATA_INTENT_KEYWORDS = [
        # Interrogative / instruction verbs
        'how', 'what', 'which', 'where', 'when', 'who',
        'show', 'list', 'find', 'display', 'give', 'tell',
        'count', 'total', 'sum', 'average', 'avg', 'max', 'min',
        'top', 'bottom', 'first', 'last',
        'compare', 'rank', 'group',
        # Data nouns
        'row', 'record', 'entry', 'entries', 'data', 'table',
        'communication', 'communications', 'message', 'messages',
        'email', 'emails', 'sms', 'sent', 'receiver', 'recipient', 'sender',
        'status', 'failed', 'success', 'succeeded', 'dropped', 'bounce', 'bounced',
        'duplicate', 'error', 'errors',
        'trade', 'trades', 'stock', 'broker', 'client', 'clients',
        'application', 'applications', 'app',
        'user', 'users',
        'date', 'today', 'yesterday', 'week', 'month', 'year',
        'percentage', 'percent', 'ratio', 'distribution', 'volume',
        # Question keywords common in NL queries
        'percentage', 'percent', 'ratio', 'distribution',
    ]
    question_lower = question.lower()
    for keyword in DANGEROUS_INTENT_KEYWORDS:
        if not any(kw in question_lower for kw in DATA_INTENT_KEYWORDS):
            raise HTTPException(
                status_code=400,
                detail=(
                    "This looks like a general question, not a data query. "
                    "Try asking things like 'how many communications', "
                    "'show failed messages', or 'top 10 clients by volume'."
                )
            )
        if keyword in question_lower:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Query blocked: requests containing '{keyword}' are not allowed. "
                    f"This platform only supports read-only questions about your data."
                )
            )
        
    start_time = time.time()

    try:
        # PRIMARY: MCP Bridge (AI-powered)
        result = await mcp_bridge.ask_question(
            question, user,
            table_name=request.table_name,
            database=database,
            category=request.category,
        )

        _log_query(user, question, result)
        return result

    except Exception as e:
        log_error("QUERY_ENDPOINT", str(e), user_id=user.get("user_id"), endpoint="POST /api/v1/query")
        raise HTTPException(status_code=500, detail=f"Query processing failed: {str(e)}")


# ═══════════════════════════════════════════════════════════════
# GET /api/v1/query/schema
# ═══════════════════════════════════════════════════════════════

@router.get("/schema", response_model=SchemaResponse)
async def view_schema(user: dict = Depends(get_current_user)):
    try:
        schema = await mcp_bridge.get_schema("CommunicationsRequestStatus")
        if schema and "error" not in schema.lower():
            return {"schema_text": schema}
    except Exception:
        pass
    schema = get_live_schema()
    return {"schema_text": schema}


# ═══════════════════════════════════════════════════════════════
# HELPER: Log query
# ═══════════════════════════════════════════════════════════════

def _log_query(user: dict, question: str, result: dict):
    try:
        execute_non_query(
            """
            INSERT INTO QueryLog
                (user_id, query_text, generated_sql, method, result_count,
                 execution_time_ms, was_successful, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, GETDATE())
            """,
            (
                user.get("user_id"),
                question,
                result.get("generated_sql") or "",
                result.get("method", "unknown"),
                result.get("row_count", 0),
                result.get("execution_time_ms", 0),
                1 if result.get("error") is None else 0,
            ),
        )
    except Exception as e:
        log_error("QUERY_LOG", str(e), user_id=user.get("user_id"), endpoint="_log_query")

# ═══════════════════════════════════════════════════════════════
# POST /api/v1/query/export-csv — Download full results as CSV
# ═══════════════════════════════════════════════════════════════

from fastapi.responses import StreamingResponse
import csv
import io
import re


class ExportRequest(BaseModel):
    sql: str
    database: Optional[str] = None


@router.post("/export-csv")
async def export_csv(
    request: ExportRequest,
    user: dict = Depends(get_current_user),
):
    """
    Re-execute a previously-generated SQL and stream the full result as CSV.
    Uses a high row cap (50,000) so CSV contains all data, not just the UI preview.
    Re-validates SQL for safety.
    """
    sql = (request.sql or "").strip()
    database = request.database or DEFAULT_DATABASE

    # Re-validate: SELECT only, no dangerous keywords
    if not sql.upper().startswith("SELECT"):
        raise HTTPException(status_code=400, detail="Only SELECT queries can be exported")

    DANGEROUS = ['DROP', 'DELETE', 'INSERT', 'UPDATE', 'ALTER',
                 'CREATE', 'EXEC', 'EXECUTE', 'TRUNCATE', 'GRANT', 'REVOKE']
    for kw in DANGEROUS:
        if re.search(rf'\b{kw}\b', sql.upper()):
            raise HTTPException(status_code=400, detail=f"Export blocked: {kw} not allowed")

    # Execute with high cap via MCP
    # Execute with high cap via MCP
    # Execute with high cap via MCP (direct call, not subprocess)
    try:
        data, columns, total, truncated, error = mcp_bridge.execute_for_export(
            sql=sql, database=database, max_rows=50000
        )
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"\n═══ EXPORT CSV EXCEPTION ═══\n{tb}\n═══════════════════════════\n", file=__import__('sys').stderr, flush=True)
        raise HTTPException(status_code=500, detail=f"Export crashed: {type(e).__name__}: {str(e)}")

    if error:
        print(f"\n═══ EXPORT CSV ERROR ═══\nError string: {error}\n═══════════════════════\n", file=__import__('sys').stderr, flush=True)
        raise HTTPException(status_code=500, detail=f"Export failed: {error}")

    # Build CSV in memory
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    for row in data:
        writer.writerow([row.get(c, "") for c in columns])
    buffer.seek(0)

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="query_results.csv"',
            "X-Row-Count": str(total),
            "X-Truncated": "true" if truncated else "false",
        },
    )


# ═══════════════════════════════════════════════════════════════
# GET /api/v1/query/categories — List categories for a database
# ═══════════════════════════════════════════════════════════════

class CategoryInfo(BaseModel):
    category: str
    description: str
    tables: List[str]
    default_table: str


class CategoriesResponse(BaseModel):
    categories: List[CategoryInfo]
    default: Optional[str]


@router.get("/categories", response_model=CategoriesResponse)
async def list_categories(
    database: str = QueryParam(default=None),
    user: dict = Depends(get_current_user),
):
    """
    Returns categories defined for the selected database.
    A category groups related tables (e.g., Communications: CommunicationMaster
    + CommunicationErrorMaster + ApplicationMaster) that should be queried
    together with FK-aware JOINs.
    """
    db = database or DEFAULT_DATABASE
    db_cfg = DATABASES.get(db, {})
    cats_cfg = db_cfg.get("categories", {}) or {}

    categories = []
    for cat_name, cat_info in cats_cfg.items():
        categories.append(CategoryInfo(
            category=cat_name,
            description=cat_info.get("description", ""),
            tables=cat_info.get("tables", []),
            default_table=cat_info.get("default_table", ""),
        ))

    default_cat = next(iter(cats_cfg.keys()), None) if cats_cfg else None
    return CategoriesResponse(categories=categories, default=default_cat)