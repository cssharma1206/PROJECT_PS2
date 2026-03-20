import sys
import os

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

import pyodbc
from datetime import datetime


# ========== DATABASE CONNECTION ==========
def get_db_connection():
    """Direct database connection"""
    return pyodbc.connect(
        "DRIVER={ODBC Driver 17 for SQL Server};"
        "SERVER=GLADIATOR\\SQLEXPRESS;"
        "DATABASE=anandrathi;"
        "Trusted_Connection=yes;"
    )


def analyze_data_quality():
    """Analyze the quality and distribution of data in the database"""
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    print("=" * 70)
    print("📊 DATA QUALITY ANALYSIS REPORT")
    print("=" * 70)
    
    # Total records
    cursor.execute("SELECT COUNT(*) FROM CommunicationsRequestStatus")
    total = cursor.fetchone()[0]
    print(f"\n📈 Total Records: {total}")
    
    # Status distribution
    print("\n🔄 Status Distribution:")
    cursor.execute("""
        SELECT LastStatus, COUNT(*) as count 
        FROM CommunicationsRequestStatus 
        GROUP BY LastStatus 
        ORDER BY count DESC
    """)
    status_data = cursor.fetchall()
    for status, count in status_data:
        percentage = (count / total) * 100 if total > 0 else 0
        print(f"  • {status:15s}: {count:5d} ({percentage:5.1f}%)")
    
    # Unique clients
    cursor.execute("SELECT COUNT(DISTINCT Receiver) FROM CommunicationsRequestStatus")
    unique_clients = cursor.fetchone()[0]
    print(f"\n👥 Unique Clients: {unique_clients}")
    
    # Unique vendors
    cursor.execute("SELECT COUNT(DISTINCT ReferenceVendorId) FROM CommunicationsRequestStatus")
    unique_vendors = cursor.fetchone()[0]
    print(f"🏢 Unique Vendors: {unique_vendors}")
    
    # Unique senders
    cursor.execute("SELECT COUNT(DISTINCT Sender) FROM CommunicationsRequestStatus")
    unique_senders = cursor.fetchone()[0]
    print(f"📧 Unique Senders: {unique_senders}")
    
    # Date range
    cursor.execute("""
        SELECT MIN(SubmitDate), MAX(SubmitDate) 
        FROM CommunicationsRequestStatus
    """)
    result = cursor.fetchone()
    if result[0] and result[1]:
        min_date, max_date = result
        print(f"\n📅 Date Range:")
        print(f"  • Earliest: {min_date}")
        print(f"  • Latest:   {max_date}")
    
    # Top 5 clients
    print("\n🔝 Top 5 Most Active Clients:")
    cursor.execute("""
        SELECT TOP 5 Receiver, COUNT(*) as count 
        FROM CommunicationsRequestStatus 
        GROUP BY Receiver 
        ORDER BY count DESC
    """)
    top_clients = cursor.fetchall()
    for idx, (client, count) in enumerate(top_clients, 1):
        print(f"  {idx}. {client:30s} - {count} communications")
    
    # Failed communications by vendor
    print("\n❌ Failed Communications by Vendor:")
    cursor.execute("""
        SELECT ReferenceVendorId, COUNT(*) as count 
        FROM CommunicationsRequestStatus 
        WHERE LastStatus = 'FAILED'
        GROUP BY ReferenceVendorId 
        ORDER BY count DESC
    """)
    failed_vendors = cursor.fetchall()
    for vendor_id, count in failed_vendors[:5]:
        print(f"  • Vendor {vendor_id:3d}: {count} failures")
    
    # Attachment distribution
    print("\n📎 Attachment Types:")
    cursor.execute("""
        SELECT AttachmentInfo, COUNT(*) as count 
        FROM CommunicationsRequestStatus 
        GROUP BY AttachmentInfo 
        ORDER BY count DESC
    """)
    attachments = cursor.fetchall()
    for attachment, count in attachments[:7]:
        if attachment:
            print(f"  • {attachment:30s}: {count}")
        else:
            print(f"  • No attachment                : {count}")
    
    # Category distribution
    print("\n📂 Category Distribution:")
    cursor.execute("""
        SELECT CategoryId, COUNT(*) as count 
        FROM CommunicationsRequestStatus 
        GROUP BY CategoryId 
        ORDER BY CategoryId
    """)
    categories = cursor.fetchall()
    for cat_id, count in categories:
        print(f"  • Category {cat_id:2d}: {count:4d} records")
    
    # Data quality checks
    print("\n✅ Data Quality Checks:")
    
    # Check for NULL receivers
    cursor.execute("SELECT COUNT(*) FROM CommunicationsRequestStatus WHERE Receiver IS NULL")
    null_receivers = cursor.fetchone()[0]
    print(f"  • NULL receivers: {null_receivers} {'✓ OK' if null_receivers == 0 else '⚠️ WARNING'}")
    
    # Check for duplicate tracking IDs
    cursor.execute("""
        SELECT COUNT(*) FROM (
            SELECT TrackingId, COUNT(*) as cnt 
            FROM CommunicationsRequestStatus 
            GROUP BY TrackingId 
            HAVING COUNT(*) > 1
        ) as duplicates
    """)
    duplicate_tracking = cursor.fetchone()[0]
    print(f"  • Duplicate TrackingIds: {duplicate_tracking} {'✓ OK' if duplicate_tracking == 0 else '⚠️ WARNING'}")
    
    # Check date consistency (UpdatedDate >= SubmitDate)
    cursor.execute("""
        SELECT COUNT(*) 
        FROM CommunicationsRequestStatus 
        WHERE UpdatedDate < SubmitDate
    """)
    invalid_dates = cursor.fetchone()[0]
    print(f"  • Invalid dates: {invalid_dates} {'✓ OK' if invalid_dates == 0 else '⚠️ WARNING'}")
    
    conn.close()
    
    print("\n" + "=" * 70)
    print("✅ Analysis Complete!")
    print("=" * 70)


def test_realistic_queries():
    """Test queries that will be used by MCP/AI"""
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    print("\n" + "=" * 70)
    print("🧪 TESTING REALISTIC QUERIES")
    print("=" * 70)
    
    # Query 1: Failed communications in last 7 days
    print("\n1️⃣ Failed communications in last 7 days:")
    cursor.execute("""
        SELECT COUNT(*) 
        FROM CommunicationsRequestStatus 
        WHERE LastStatus = 'FAILED' 
        AND SubmitDate >= DATEADD(day, -7, GETDATE())
    """)
    result = cursor.fetchone()[0]
    print(f"   Result: {result} records")
    
    # Query 2: Communications for a specific client
    print("\n2️⃣ Communications for client1@gmail.com:")
    cursor.execute("""
        SELECT COUNT(*) 
        FROM CommunicationsRequestStatus 
        WHERE Receiver = 'client1@gmail.com'
    """)
    result = cursor.fetchone()[0]
    print(f"   Result: {result} records")
    
    # Query 3: Pending communications by vendor
    print("\n3️⃣ Pending communications grouped by vendor:")
    cursor.execute("""
        SELECT ReferenceVendorId, COUNT(*) as count 
        FROM CommunicationsRequestStatus 
        WHERE LastStatus = 'PENDING'
        GROUP BY ReferenceVendorId
        ORDER BY count DESC
    """)
    results = cursor.fetchall()
    for vendor, count in results[:3]:
        print(f"   Vendor {vendor}: {count} pending")
    
    # Query 4: Trade confirmations sent
    print("\n4️⃣ Trade confirmations sent:")
    cursor.execute("""
        SELECT COUNT(*) 
        FROM CommunicationsRequestStatus 
        WHERE AttachmentInfo = 'trade_confirmation.pdf'
        AND LastStatus = 'SENT'
    """)
    result = cursor.fetchone()[0]
    print(f"   Result: {result} records")
    
    conn.close()
    
    print("\n" + "=" * 70)


if __name__ == "__main__":
    analyze_data_quality()
    test_realistic_queries()