"""
Configuration - Centralized settings for the entire backend.
All database connections, JWT secrets, and app settings live here.
NO hardcoded connection strings anywhere else in the project.
"""

import os
from datetime import timedelta


# ═══════════════════════════════════════════════════════════════
# DATABASE CONFIGURATION
# ═══════════════════════════════════════════════════════════════
DB_DRIVER = os.getenv("DB_DRIVER", "{ODBC Driver 17 for SQL Server}")
DB_SERVER = os.getenv("DB_SERVER", r"GLADIATOR\SQLEXPRESS")
DB_NAME = os.getenv("DB_NAME", "anandrathi")
DB_TRUSTED = os.getenv("DB_TRUSTED", "yes")

# Connection string builder
def get_connection_string():
    return (
        f"DRIVER={DB_DRIVER};"
        f"SERVER={DB_SERVER};"
        f"DATABASE={DB_NAME};"
        f"Trusted_Connection={DB_TRUSTED};"
    )


# ═══════════════════════════════════════════════════════════════
# JWT CONFIGURATION
# ═══════════════════════════════════════════════════════════════
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "anand_rathi_phase2_secret_2026")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 7


# ═══════════════════════════════════════════════════════════════
# APP CONFIGURATION
# ═══════════════════════════════════════════════════════════════
APP_TITLE = "Anand Rathi - Communications Intelligence Platform"
APP_VERSION = "1.0.0"
APP_DESCRIPTION = "Category-mode NLQ with FK-aware multi-table JOINs, ApplicationAccessMaster authorization, and dynamic live-schema prompt building"
API_PREFIX = "/api/v1"

# CORS - allowed origins for frontend
CORS_ORIGINS = [
    "http://localhost:3000",    # React dev server
    "http://localhost:5173",    # Vite dev server
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
]
