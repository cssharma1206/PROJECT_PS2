"""
═══════════════════════════════════════════════════════════════════
ANAND RATHI - Communications Intelligence Platform
Phase 2: FastAPI Backend Server
═══════════════════════════════════════════════════════════════════

Run with:  uvicorn app.main:app --reload --port 8000
Swagger:   http://localhost:8000/docs
ReDoc:     http://localhost:8000/redoc
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import APP_TITLE, APP_VERSION, APP_DESCRIPTION, API_PREFIX, CORS_ORIGINS
from app.routers import auth, dashboard, admin, query

# ─── Create FastAPI App ───────────────────────────────────────
app = FastAPI(
    title=APP_TITLE,
    version=APP_VERSION,
    description=APP_DESCRIPTION,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ─── CORS Middleware ──────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Register Routers ────────────────────────────────────────
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(dashboard.router, prefix=API_PREFIX)
app.include_router(admin.router, prefix=API_PREFIX)
app.include_router(query.router)  # No prefix — router has /api/v1/query built in


# ─── Root Endpoint ────────────────────────────────────────────
@app.get("/", tags=["Health"])
def root():
    return {
        "application": APP_TITLE,
        "version": APP_VERSION,
        "status": "running",
        "docs": "/docs",
        "api_prefix": API_PREFIX,
        "endpoints": {
            "auth": f"{API_PREFIX}/auth/login",
            "query": "/api/v1/query",
            "schema": "/api/v1/query/schema",
            "dashboard": f"{API_PREFIX}/dashboard/stats",
            "admin": f"{API_PREFIX}/admin/users",
        }
    }


@app.get("/health", tags=["Health"])
def health_check():
    """Health check endpoint — checks DB + Ollama status."""
    from app.services.database import get_db_connection
    import requests as req

    # Check DB
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"

    # Check Ollama
    try:
        r = req.get("http://localhost:11434/api/tags", timeout=3)
        if r.status_code == 200:
            models = [m["name"] for m in r.json().get("models", [])]
            ollama_status = f"running ({', '.join(models)})"
        else:
            ollama_status = "running (no models)"
    except Exception:
        ollama_status = "not running"

    return {
        "status": "healthy",
        "database": db_status,
        "ollama": ollama_status,
        "version": APP_VERSION,
    }
