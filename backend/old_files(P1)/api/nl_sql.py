from fastapi import APIRouter
from pydantic import BaseModel

from backend.llm.sql_generator import generate_sql_from_question
from backend.db.operations import execute_sql_query
from backend.models import Question
from backend.db.operations import get_last_failed
from backend.db.operations import get_last_by_status
router = APIRouter()


class NLQuery(BaseModel):
    question: str


@router.post("/api/nl-sql")
def nl_sql(req: Question):
    q = req.question.lower()

    if "failed" in q:
        return get_last_failed()
    if "success" in q:
        return get_last_by_status("SUCCESS", 10)
    if "pending" in q:
        return get_last_by_status("PENDING", 10)
    
    return {"error": "Query not supported yet"}

    

