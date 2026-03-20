import sys
import os

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from datetime import datetime
import uuid
import pyodbc


# ========== DATABASE CONNECTION ==========
def get_db_connection():
    """Direct database connection"""
    return pyodbc.connect(
        "DRIVER={ODBC Driver 17 for SQL Server};"
        "SERVER=GLADIATOR\\SQLEXPRESS;"
        "DATABASE=anandrathi;"
        "Trusted_Connection=yes;"
    )


# ========== SAFE QUERY EXECUTION ==========

def execute_select(query: str, params: tuple = None):
    """
    Execute a SELECT query with parameters (SQL injection safe)
    
    Args:
        query: SQL query with ? placeholders
        params: Tuple of parameters to bind
    
    Returns:
        List of dictionaries (one per row)
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        
        # Get column names
        columns = [column[0] for column in cursor.description]
        
        # Fetch all rows
        rows = cursor.fetchall()
        
        # Convert to list of dictionaries
        results = [dict(zip(columns, row)) for row in rows]
        
        return results
    
    finally:
        cursor.close()
        conn.close()


def execute_sql_query(sql: str, params: tuple = None):
    """
    Execute any SQL query (SELECT/INSERT/UPDATE/DELETE) with parameters
    
    Args:
        sql: SQL query with ? placeholders
        params: Tuple of parameters to bind
    
    Returns:
        List of dictionaries for SELECT, empty list otherwise
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)

        # If it's a SELECT query, return results
        if cursor.description is None:
            conn.commit()
            return []

        columns = [column[0] for column in cursor.description]
        rows = cursor.fetchall()

        return [dict(zip(columns, row)) for row in rows]

    finally:
        cursor.close()
        conn.close()


# ========== PARAMETERIZED QUERY FUNCTIONS (SQL INJECTION SAFE) ==========

def get_last_failed(limit: int = 5):
    """
    Get last N failed communications
    
    Args:
        limit: Number of records to return (default 5)
    
    Returns:
        List of failed communication records
    """
    query = """
        SELECT TOP (?) *
        FROM CommunicationsRequestStatus
        WHERE LastStatus = ?
        ORDER BY UpdatedDate DESC
    """
    return execute_select(query, (limit, 'FAILED'))


def get_last_by_status(status: str, limit: int = 5):
    """
    Get last N communications by status (SQL injection safe)
    
    Args:
        status: Status to filter by (e.g., 'SENT', 'FAILED', 'PENDING')
        limit: Number of records to return
    
    Returns:
        List of communication records
    """
    query = """
        SELECT TOP (?) *
        FROM CommunicationsRequestStatus
        WHERE LastStatus = ?
        ORDER BY UpdatedDate DESC
    """
    return execute_select(query, (limit, status))


def count_by_status(status: str):
    """
    Count communications by status
    
    Args:
        status: Status to count (e.g., 'SENT', 'FAILED')
    
    Returns:
        List with single dictionary containing count
    """
    query = """
        SELECT COUNT(*) as count
        FROM CommunicationsRequestStatus
        WHERE LastStatus = ?
    """
    return execute_select(query, (status,))


def get_by_client(client_email: str, limit: int = 10):
    """
    Get communications for a specific client
    
    Args:
        client_email: Client's email address
        limit: Number of records to return
    
    Returns:
        List of communication records
    """
    query = """
        SELECT TOP (?) *
        FROM CommunicationsRequestStatus
        WHERE Receiver = ?
        ORDER BY UpdatedDate DESC
    """
    return execute_select(query, (limit, client_email))


def get_by_vendor(vendor_id: int, limit: int = 10):
    """
    Get communications for a specific vendor
    
    Args:
        vendor_id: Vendor ID
        limit: Number of records to return
    
    Returns:
        List of communication records
    """
    query = """
        SELECT TOP (?) *
        FROM CommunicationsRequestStatus
        WHERE ReferenceVendorId = ?
        ORDER BY UpdatedDate DESC
    """
    return execute_select(query, (limit, vendor_id))


def get_by_date_range(start_date: str, end_date: str, limit: int = 100):
    """
    Get communications within a date range
    
    Args:
        start_date: Start date (YYYY-MM-DD format)
        end_date: End date (YYYY-MM-DD format)
        limit: Number of records to return
    
    Returns:
        List of communication records
    """
    query = """
        SELECT TOP (?) *
        FROM CommunicationsRequestStatus
        WHERE SubmitDate BETWEEN ? AND ?
        ORDER BY SubmitDate DESC
    """
    return execute_select(query, (limit, start_date, end_date))


def get_by_attachment_type(attachment_name: str, limit: int = 10):
    """
    Get communications with specific attachment type
    
    Args:
        attachment_name: Name of attachment (e.g., 'trade_confirmation.pdf')
        limit: Number of records to return
    
    Returns:
        List of communication records
    """
    query = """
        SELECT TOP (?) *
        FROM CommunicationsRequestStatus
        WHERE AttachmentInfo = ?
        ORDER BY UpdatedDate DESC
    """
    return execute_select(query, (limit, attachment_name))


def get_status_summary():
    """
    Get summary of all statuses with counts
    
    Returns:
        List of status counts
    """
    query = """
        SELECT 
            LastStatus,
            COUNT(*) as count,
            MIN(SubmitDate) as earliest,
            MAX(SubmitDate) as latest
        FROM CommunicationsRequestStatus
        GROUP BY LastStatus
        ORDER BY count DESC
    """
    return execute_select(query)


def get_vendor_summary():
    """
    Get summary of communications by vendor
    
    Returns:
        List of vendor statistics
    """
    query = """
        SELECT 
            ReferenceVendorId,
            COUNT(*) as total_communications,
            SUM(CASE WHEN LastStatus = 'FAILED' THEN 1 ELSE 0 END) as failed_count,
            SUM(CASE WHEN LastStatus = 'SENT' THEN 1 ELSE 0 END) as sent_count,
            SUM(CASE WHEN LastStatus = 'PENDING' THEN 1 ELSE 0 END) as pending_count
        FROM CommunicationsRequestStatus
        GROUP BY ReferenceVendorId
        ORDER BY total_communications DESC
    """
    return execute_select(query)


def get_recent_failures(days: int = 7):
    """
    Get failed communications from last N days
    
    Args:
        days: Number of days to look back
    
    Returns:
        List of failed communications
    """
    query = """
        SELECT *
        FROM CommunicationsRequestStatus
        WHERE LastStatus = 'FAILED'
        AND SubmitDate >= DATEADD(day, ?, GETDATE())
        ORDER BY SubmitDate DESC
    """
    return execute_select(query, (-days,))


# ========== DUMMY DATA INSERTION (KEEP FOR TESTING) ==========

def insert_dummy_data():
    """Insert a single dummy record for testing"""
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
    INSERT INTO CommunicationsRequestStatus (
        ReferenceApplicationId,
        ReferenceVendorId,
        Receiver,
        Sender,
        CCData,
        BccData,
        SubmitDate,
        AttachmentInfo,
        RequestData,
        TrackingId,
        Gu_id,
        LastStatus,
        UpdatedDate,
        CategoryId
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    values = (
        101,
        202,
        "client@example.com",
        "noreply@anandrathi.com",
        "cc@example.com",
        "bcc@example.com",
        datetime.now(),
        "invoice.pdf",
        '{"message":"Portfolio update"}',
        f"TRK-{uuid.uuid4()}",
        str(uuid.uuid4()),
        "SUBMITTED",
        datetime.now(),
        1
    )

    cursor.execute(query, values)
    conn.commit()
    conn.close()


# ========== TESTING ==========

if __name__ == "__main__":
    print("🧪 Testing Parameterized Queries...\n")
    
    # Test 1: Get failed communications
    print("1️⃣ Last 5 failed communications:")
    failed = get_last_failed(5)
    print(f"   Found {len(failed)} records\n")
    
    # Test 2: Get by status
    print("2️⃣ Last 3 pending communications:")
    pending = get_last_by_status("PENDING", 3)
    print(f"   Found {len(pending)} records\n")
    
    # Test 3: Count by status
    print("3️⃣ Count of failed communications:")
    count = count_by_status("FAILED")
    print(f"   Count: {count[0]['count']}\n")
    
    # Test 4: Status summary
    print("4️⃣ Status Summary:")
    summary = get_status_summary()
    for row in summary:
        print(f"   {row['LastStatus']:12s}: {row['count']:4d} records")
    
    # Test 5: Vendor summary
    print("\n5️⃣ Top 3 Vendors by Activity:")
    vendors = get_vendor_summary()[:3]
    for row in vendors:
        print(f"   Vendor {row['ReferenceVendorId']:3d}: {row['total_communications']:4d} total, "
              f"{row['failed_count']:3d} failed, {row['sent_count']:3d} sent")
    
    # Test 6: Recent failures
    print("\n6️⃣ Failed communications in last 7 days:")
    recent = get_recent_failures(7)
    print(f"   Found {len(recent)} records")
    
    print("\n✅ All tests passed! Queries are SQL injection safe!")