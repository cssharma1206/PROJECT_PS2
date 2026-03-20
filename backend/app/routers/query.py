"""
Query Router - /api/v1/query
=============================
The API endpoint for natural language queries.

Endpoints:
  POST /api/v1/query          - Process a natural language question
  GET  /api/v1/query/schema   - Get live database schema (for dev/debug)
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from app.middleware.auth_middleware import get_current_user
from app.services.nlq_engine import process_query, get_live_schema
from app.services.database import execute_non_query
from app.services.error_logger import log_error

router = APIRouter(prefix="/api/v1/query", tags=["Query"])


# ═══════════════════════════════════════════════════════════════
# PYDANTIC MODELS
# ═══════════════════════════════════════════════════════════════

class QueryRequest(BaseModel):
    question: str


class QueryResponse(BaseModel):
    question: str
    generated_sql: Optional[str]
    method: str  # "template", "ai", or "failed"
    data: List[Dict[str, Any]]
    columns: List[str]
    row_count: int
    execution_time_ms: int
    insights: List[str]
    error: Optional[str]


class SchemaResponse(BaseModel):
    schema_text: str


# ═══════════════════════════════════════════════════════════════
# POST /api/v1/query — Main query endpoint
# ═══════════════════════════════════════════════════════════════

@router.post("", response_model=QueryResponse)
async def natural_language_query(
    request: QueryRequest,
    user: dict = Depends(get_current_user)
):
    """
    Process a natural language question and return SQL + data.

    Flow:
      1. Authenticate user via JWT token
      2. Try template matching (instant, no AI)
      3. Fall back to Ollama AI if no template match
      4. Validate generated SQL (security)
      5. Inject access control (guaranteed data isolation)
      6. Execute SQL on database
      7. Log query to QueryLog table
      8. Return results + metadata

    Request:
        { "question": "Show me failed emails last 7 days" }

    Response:
        {
            "question": "...",
            "generated_sql": "SELECT ...",
            "method": "template",
            "data": [{...}, {...}],
            "columns": ["Id", "Receiver", ...],
            "row_count": 15,
            "execution_time_ms": 42,
            "insights": ["Found 15 records."],
            "error": null
        }
    """
    question = request.question.strip()

    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    if len(question) < 3:
        raise HTTPException(status_code=400, detail="Question too short")

    if len(question) > 500:
        raise HTTPException(status_code=400, detail="Question too long (max 500 characters)")

    try:
        # Process the query through the NLQ engine
        result = process_query(question, user)

        # Log to QueryLog table
        _log_query(
            user_id=user.get("user_id"),
            username=user.get("username"),
            question=question,
            generated_sql=result.get("generated_sql"),
            method=result.get("method"),
            row_count=result.get("row_count", 0),
            execution_time_ms=result.get("execution_time_ms", 0),
            success=result.get("error") is None,
        )

        return result

    except Exception as e:
        log_error("QUERY_ENDPOINT", str(e), user_id=user.get("user_id"), endpoint="POST /api/v1/query")
        raise HTTPException(status_code=500, detail=f"Query processing failed: {str(e)}")


# ═══════════════════════════════════════════════════════════════
# GET /api/v1/query/schema — View live schema (debug/dev)
# ═══════════════════════════════════════════════════════════════

@router.get("/schema", response_model=SchemaResponse)
async def view_schema(user: dict = Depends(get_current_user)):
    """
    Returns the live database schema as read from INFORMATION_SCHEMA.
    Useful for debugging and showing supervisors that schema is dynamic.
    """
    schema = get_live_schema()
    return {"schema_text": schema}


# ═══════════════════════════════════════════════════════════════
# HELPER: Log query to QueryLog table
# ═══════════════════════════════════════════════════════════════

def _log_query(
    user_id: int,
    username: str,
    question: str,
    generated_sql: str,
    method: str,
    row_count: int,
    execution_time_ms: int,
    success: bool,
):
    """Log every query to the QueryLog table for audit trail."""
    try:
        execute_non_query(
            """
            INSERT INTO QueryLog
                (UserId, Username, Question, GeneratedSQL, Method, RowCount,
                 ExecutionTimeMs, Success, CreatedAt)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, GETDATE())
            """,
            (
                user_id,
                username,
                question,
                generated_sql or "",
                method,
                row_count,
                execution_time_ms,
                1 if success else 0,
            ),
        )
    except Exception as e:
        # Don't fail the request if logging fails
        log_error("QUERY_LOG", str(e), user_id=user_id, endpoint="_log_query")
