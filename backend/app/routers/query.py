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
from app.services.nlq_engine import (
    match_template, validate_sql, inject_access_filter,
    execute_query_safe, get_live_schema,
)
from app.services.database import execute_non_query
from app.services.error_logger import log_error

router = APIRouter(prefix="/api/v1/query", tags=["Query"])

ENABLE_TEMPLATE_CACHE = True


# ═══════════════════════════════════════════════════════════════
# PYDANTIC MODELS
# ═══════════════════════════════════════════════════════════════

class QueryRequest(BaseModel):
    question: str
    table_name: Optional[str] = None
    database: Optional[str] = None


class QueryResponse(BaseModel):
    question: str
    generated_sql: Optional[str]
    method: str
    data: List[Dict[str, Any]]
    columns: List[str]
    row_count: int
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
# HELPER: Build access filter
# ═══════════════════════════════════════════════════════════════

def _build_access_filter(user: dict) -> str:
    role = user.get("role", "")
    app_id = user.get("application_id")
    if role == "Admin":
        return ""
    elif app_id and role in ("RM_Head", "RM", "RM_Head2", "RM2", "RM3"):
        return f"ReferenceApplicationId = {app_id}"
    else:
        username = user.get("username", "")
        return f"Receiver LIKE '%{username}%'"


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

    start_time = time.time()
    access_filter = _build_access_filter(user)

    try:
        # Template cache only for default database + default table
        if (ENABLE_TEMPLATE_CACHE
            and database == DEFAULT_DATABASE
            and table_name == "CommunicationsRequestStatus"):

            sql, description = match_template(question, access_filter)
            if sql is not None:
                is_valid, reason = validate_sql(sql)
                if is_valid:
                    sql = inject_access_filter(sql, access_filter)
                    data, columns, error = execute_query_safe(sql)
                    elapsed = int((time.time() - start_time) * 1000)

                    insights = []
                    if len(data) == 0:
                        insights.append("No records found.")
                    else:
                        insights.append(f"Found {len(data)} records.")
                    insights.append(f"Instant match: {description}")

                    result = {
                        "question": question,
                        "generated_sql": sql,
                        "method": "template",
                        "data": data,
                        "columns": columns,
                        "row_count": len(data),
                        "execution_time_ms": elapsed,
                        "insights": insights,
                        "error": error,
                    }

                    _log_query(user, question, result)
                    return result

        # PRIMARY: MCP Bridge (AI-powered)
        result = await mcp_bridge.ask_question(
            question, user,
            table_name=table_name,
            database=database,
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