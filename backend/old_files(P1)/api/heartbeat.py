from fastapi import APIRouter
from backend.db.connection import get_db_connection


router = APIRouter()

@router.get("/heartbeat")
def heartbeat():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        conn.close()
        return {"status": "UP", "database": "CONNECTED"}
    except Exception as e:
        return {"status": "DOWN", "error": str(e)}
