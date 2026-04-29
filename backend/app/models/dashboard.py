"""
Dashboard & Query Models - Pydantic schemas for dashboard and query endpoints.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime


# ─── DASHBOARD MODELS ─────────────────────────────────────────

class DashboardStats(BaseModel):
    sent: int = 0
    failed: int = 0
    pending: int = 0
    total: int = 0
    success_rate: float = 0.0


class ChartDataPoint(BaseModel):
    label: str
    value: int


class StatusChartResponse(BaseModel):
    chart_type: str = "pie"
    title: str = "Status Distribution"
    data: List[ChartDataPoint]


class TrendDataPoint(BaseModel):
    date: str
    total: int
    sent: int = 0
    failed: int = 0


class TrendChartResponse(BaseModel):
    chart_type: str = "line"
    title: str = "Daily Trend"
    days: int
    data: List[TrendDataPoint]


class VendorDataPoint(BaseModel):
    vendor_id: int
    total: int
    sent: int = 0
    failed: int = 0
    pending: int = 0
    success_rate: float = 0.0


class VendorChartResponse(BaseModel):
    chart_type: str = "bar"
    title: str = "Vendor Performance"
    data: List[VendorDataPoint]


class TopClient(BaseModel):
    receiver: str
    total: int
    failed: int = 0


class TopClientsResponse(BaseModel):
    title: str = "Top Clients"
    data: List[TopClient]


# ─── QUERY MODELS ─────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000, examples=["Show failed emails from vendor 7"])


class QueryResponse(BaseModel):
    question: str
    generated_sql: str
    method: str
    data: List[dict]
    columns: List[str]
    row_count: int
    execution_time_ms: int
    insights: List[str] = []


class QueryHistoryItem(BaseModel):
    log_id: int
    query_text: str
    generated_sql: Optional[str]
    method: Optional[str]
    result_count: int
    was_successful: bool
    created_at: str


class QueryHistoryResponse(BaseModel):
    queries: List[QueryHistoryItem]
    total: int
    page: int
    limit: int


# ─── ADMIN MODELS ─────────────────────────────────────────────

class UserListItem(BaseModel):
    user_id: int
    username: str
    email: str
    full_name: str
    role_name: str
    is_active: bool
    last_login: Optional[str]


class UserListResponse(BaseModel):
    users: List[UserListItem]
    total: int


class ErrorLogItem(BaseModel):
    error_id: int
    error_type: str
    error_message: str
    endpoint: Optional[str]
    created_at: str


class ErrorLogResponse(BaseModel):
    errors: List[ErrorLogItem]
    total: int


# ─── Trading Dashboard Models ────────────────────────────────────────────
 
class TradeTypeBreakdown(BaseModel):
    """One row of BUY vs SELL split."""
    trade_type: str       # "BUY" or "SELL"
    count: int
 
class TopSymbol(BaseModel):
    """One row of top traded symbols."""
    symbol: str
    count: int
 
class TradingStats(BaseModel):
    """All Trading dashboard KPIs in one payload."""
    total_trades: int = 0
    total_value: float = 0.0
    avg_trade_size: float = 0.0
    by_type: list[TradeTypeBreakdown] = []
    top_symbols: list[TopSymbol] = []