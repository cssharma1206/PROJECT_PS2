"""
Dashboard Router - API endpoints for dashboard data.
  GET /api/v1/dashboard/stats          - KPI counts (sent, failed, pending, total)
  GET /api/v1/dashboard/charts/status  - Status distribution (pie chart data)
  GET /api/v1/dashboard/charts/trend   - Daily trend (line chart data)
  GET /api/v1/dashboard/charts/vendors - Application breakdown (bar chart data) — was vendor in old schema
  GET /api/v1/dashboard/top-clients    - Top clients by volume

Schema notes (migrated to new 4-table schema):
  Table:    CommunicationMaster (replaces CommunicationsRequestStatus)
  Columns:  ComID, ServiceType, ApplicationId, Message,
            SentTo, SentBy, CreatedAt, Status
  Statuses: SUCCESS, FAILED, BOUNCE, DROPPED, DUPLICATE

KPI mapping (tonight — simple 3-card layout preserved):
  sent    = SUCCESS
  failed  = FAILED
  pending = BOUNCE + DROPPED + DUPLICATE   (catch-all for non-success/non-failure)

ALL endpoints are filtered by the user's role:
  - Admin:   sees ALL data
  - RM/Head: sees only their team's data (by ApplicationId)
  - Client:  sees only their own data (by SentTo)
"""

from fastapi import APIRouter, Depends, Query
from app.middleware.auth_middleware import get_current_user
from app.services.database import get_db_connection
from app.services.error_logger import log_error
from app.models.dashboard import (
    DashboardStats, StatusChartResponse, ChartDataPoint,
    TrendChartResponse, TrendDataPoint,
    VendorChartResponse, VendorDataPoint,
    TopClientsResponse, TopClient,
)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


# ═══════════════════════════════════════════════════════════════
# HELPER: Build WHERE clause based on user role
# ═══════════════════════════════════════════════════════════════

def build_access_filter(user: dict) -> str:
    """
    Build a SQL WHERE clause based on the user's role and application_id.
    This is the KEY security mechanism - data is filtered at the SQL level.

    Admin       -> no filter (sees everything)
    RM / Head   -> WHERE ApplicationId = {application_id}
    Client      -> WHERE SentTo LIKE '%{username}%'
    """
    role = user.get("role", "")

    if role == "Admin":
        return ""

    app_id = user.get("application_id")
    if app_id and role in ("RM_Head", "RM", "RM_Head2", "RM2", "RM3"):
        return f"WHERE ApplicationId = {app_id}"

    # Client - can only see their own communications
    username = user.get("username", "")
    return f"WHERE SentTo LIKE '%{username}%'"


def add_and_clause(base_filter: str, condition: str) -> str:
    """Helper to add AND clause to an existing WHERE or create a new one."""
    if base_filter:
        return f"{base_filter} AND {condition}"
    return f"WHERE {condition}"


# ═══════════════════════════════════════════════════════════════
# GET /dashboard/stats - KPI Cards
# ═══════════════════════════════════════════════════════════════

@router.get("/stats", response_model=DashboardStats)
def get_stats(user: dict = Depends(get_current_user)):
    """
    Returns 4 KPI numbers: sent, failed, pending, total.

    Status mapping for the 3-card layout:
      sent    = SUCCESS
      failed  = FAILED
      pending = BOUNCE | DROPPED | DUPLICATE  (non-success, non-failure)
    """
    access_filter = build_access_filter(user)
    conn = get_db_connection()

    try:
        cursor = conn.cursor()

        # SUCCESS -> "sent"
        where = add_and_clause(access_filter, "Status = 'SUCCESS'")
        cursor.execute(f"SELECT COUNT(*) FROM CommunicationMaster {where}")
        sent = cursor.fetchone()[0]

        # FAILED -> "failed"
        where = add_and_clause(access_filter, "Status = 'FAILED'")
        cursor.execute(f"SELECT COUNT(*) FROM CommunicationMaster {where}")
        failed = cursor.fetchone()[0]

        # BOUNCE | DROPPED | DUPLICATE -> "pending" (catch-all bucket)
        where = add_and_clause(access_filter, "Status IN ('BOUNCE', 'DROPPED', 'DUPLICATE')")
        cursor.execute(f"SELECT COUNT(*) FROM CommunicationMaster {where}")
        pending = cursor.fetchone()[0]

        # Total count (all rows)
        cursor.execute(f"SELECT COUNT(*) FROM CommunicationMaster {access_filter}")
        total = cursor.fetchone()[0]

        # Success rate based on SUCCESS vs total
        success_rate = round((sent / total * 100), 1) if total > 0 else 0.0

        cursor.close()
        return DashboardStats(
            sent=sent,
            failed=failed,
            pending=pending,
            total=total,
            success_rate=success_rate,
        )
    except Exception as e:
        log_error("DASHBOARD_STATS", str(e), user.get("user_id"), "/dashboard/stats")
        return DashboardStats()
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
# GET /dashboard/charts/status - Status Pie Chart
# ═══════════════════════════════════════════════════════════════

@router.get("/charts/status", response_model=StatusChartResponse)
def get_status_chart(user: dict = Depends(get_current_user)):
    """
    Returns status distribution (all 5 statuses) for a pie/donut chart.
    Unlike the KPI cards (which bucket to 3), the pie shows the truth.
    """
    access_filter = build_access_filter(user)
    conn = get_db_connection()

    try:
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT Status, COUNT(*) AS Count
            FROM CommunicationMaster
            {access_filter}
            GROUP BY Status
            ORDER BY Count DESC
        """)
        rows = cursor.fetchall()
        cursor.close()

        data = [ChartDataPoint(label=row[0], value=row[1]) for row in rows]
        return StatusChartResponse(data=data)

    except Exception as e:
        log_error("DASHBOARD_STATUS_CHART", str(e), user.get("user_id"), "/dashboard/charts/status")
        return StatusChartResponse(data=[])
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
# GET /dashboard/charts/trend - Daily Trend Line Chart
# ═══════════════════════════════════════════════════════════════

@router.get("/charts/trend", response_model=TrendChartResponse)
def get_trend_chart(
    days: int = Query(default=7, ge=1, le=90, description="Number of days to look back"),
    user: dict = Depends(get_current_user),
):
    """
    Returns daily counts for the last N days (default 7).
    Includes total, sent (SUCCESS), and failed per day for a multi-line chart.
    """
    access_filter = build_access_filter(user)
    date_condition = f"CreatedAt >= DATEADD(day, -{days}, GETDATE())"
    where = add_and_clause(access_filter, date_condition)

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT
                FORMAT(CreatedAt, 'yyyy-MM-dd') AS Date,
                COUNT(*) AS Total,
                SUM(CASE WHEN Status = 'SUCCESS' THEN 1 ELSE 0 END) AS Sent,
                SUM(CASE WHEN Status = 'FAILED' THEN 1 ELSE 0 END) AS Failed
            FROM CommunicationMaster
            {where}
            GROUP BY FORMAT(CreatedAt, 'yyyy-MM-dd')
            ORDER BY Date
        """)
        rows = cursor.fetchall()
        cursor.close()

        data = [
            TrendDataPoint(date=row[0], total=row[1], sent=row[2], failed=row[3])
            for row in rows
        ]
        return TrendChartResponse(days=days, data=data)

    except Exception as e:
        log_error("DASHBOARD_TREND_CHART", str(e), user.get("user_id"), "/dashboard/charts/trend")
        return TrendChartResponse(days=days, data=[])
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
# GET /dashboard/charts/vendors - Application Breakdown (was Vendor)
# ═══════════════════════════════════════════════════════════════
# Old schema grouped by ReferenceVendorId. New schema has no vendor
# concept, so we group by ApplicationId (APP001 vs APP002). Same
# response shape so frontend doesn't need changes.
# ═══════════════════════════════════════════════════════════════

@router.get("/charts/vendors", response_model=VendorChartResponse)
def get_vendor_chart(user: dict = Depends(get_current_user)):
    """
    Returns per-application performance data: total, sent, failed,
    pending (catch-all), and success rate.
    Kept on the /charts/vendors route for frontend compatibility.
    """
    access_filter = build_access_filter(user)
    conn = get_db_connection()

    try:
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT
                ApplicationId,
                COUNT(*) AS Total,
                SUM(CASE WHEN Status = 'SUCCESS' THEN 1 ELSE 0 END) AS Sent,
                SUM(CASE WHEN Status = 'FAILED' THEN 1 ELSE 0 END) AS Failed,
                SUM(CASE WHEN Status IN ('BOUNCE', 'DROPPED', 'DUPLICATE') THEN 1 ELSE 0 END) AS Pending
            FROM CommunicationMaster
            {access_filter}
            GROUP BY ApplicationId
            ORDER BY Total DESC
        """)
        rows = cursor.fetchall()
        cursor.close()

        data = []
        for row in rows:
            total = row[1]
            sent = row[2]
            rate = round((sent / total * 100), 1) if total > 0 else 0.0
            data.append(VendorDataPoint(
                vendor_id=row[0], total=total, sent=sent,
                failed=row[3], pending=row[4], success_rate=rate,
            ))
        return VendorChartResponse(data=data)

    except Exception as e:
        log_error("DASHBOARD_VENDOR_CHART", str(e), user.get("user_id"), "/dashboard/charts/vendors")
        return VendorChartResponse(data=[])
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
# GET /dashboard/top-clients - Top Clients by Volume
# ═══════════════════════════════════════════════════════════════

@router.get("/top-clients", response_model=TopClientsResponse)
def get_top_clients(
    limit: int = Query(default=10, ge=1, le=50, description="Number of top clients"),
    user: dict = Depends(get_current_user),
):
    """
    Returns top N clients ranked by communication volume.
    'Client' here = the SentTo value (recipient phone/email).
    """
    access_filter = build_access_filter(user)
    conn = get_db_connection()

    try:
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT TOP ({limit})
                SentTo,
                COUNT(*) AS Total,
                SUM(CASE WHEN Status = 'FAILED' THEN 1 ELSE 0 END) AS Failed
            FROM CommunicationMaster
            {access_filter}
            GROUP BY SentTo
            ORDER BY Total DESC
        """)
        rows = cursor.fetchall()
        cursor.close()

        data = [TopClient(receiver=row[0], total=row[1], failed=row[2]) for row in rows]
        return TopClientsResponse(data=data)

    except Exception as e:
        log_error("DASHBOARD_TOP_CLIENTS", str(e), user.get("user_id"), "/dashboard/top-clients")
        return TopClientsResponse(data=[])
    finally:
        conn.close()