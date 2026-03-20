import sys
import os

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

import uuid
import random
from datetime import datetime, timedelta
import pyodbc


# ========== DATABASE CONNECTION ==========
def get_db_connection():
    """Direct database connection (no module import needed)"""
    return pyodbc.connect(
        "DRIVER={ODBC Driver 17 for SQL Server};"
        "SERVER=GLADIATOR\\SQLEXPRESS;"
        "DATABASE=anandrathi;"
        "Trusted_Connection=yes;"
    )


# ========== REALISTIC DATA POOLS ==========

# Realistic client emails (50 different clients)
CLIENTS = [
    f"client{i}@gmail.com" for i in range(1, 26)
] + [
    f"investor{i}@yahoo.com" for i in range(1, 26)
]

# Realistic vendor IDs (different service providers)
VENDOR_IDS = [1, 2, 3, 5, 7, 10, 15, 20, 25, 30]  # 10 vendors

# Realistic senders from different departments
SENDERS = [
    "noreply@anandrathi.com",
    "trading@anandrathi.com",
    "support@anandrathi.com",
    "portfolio@anandrathi.com",
    "kyc@anandrathi.com",
    "accounts@anandrathi.com"
]

# Realistic attachment types
ATTACHMENTS = [
    "trade_confirmation.pdf",
    "portfolio_statement.pdf",
    "tax_certificate.pdf",
    "account_opening_form.pdf",
    "kyc_documents.pdf",
    "contract_note.pdf",
    "margin_call_notice.pdf",
    "dividend_summary.pdf",
    None  # Some emails have no attachments
]

# Realistic request payloads (JSON-like strings)
REQUEST_TEMPLATES = [
    '{{"type":"trade_confirmation","stock":"RELIANCE","qty":100,"price":2450.50}}',
    '{{"type":"portfolio_update","holdings":15,"total_value":500000}}',
    '{{"type":"kyc_verification","status":"pending","doc_id":"KYC123"}}',
    '{{"type":"margin_call","shortfall":50000,"deadline":"2026-02-15"}}',
    '{{"type":"dividend_credit","amount":1250,"stock":"INFY"}}',
    '{{"type":"tax_statement","financial_year":"2025-26"}}',
    '{{"type":"account_statement","month":"January","year":2026}}',
    '{{"type":"contract_note","trade_date":"2026-02-01","settlement":"T+2"}}'
]

# Status progression (realistic workflow)
STATUSES = ["CREATED", "SUBMITTED", "SENT", "DELIVERED", "FAILED", "PENDING"]

# Category IDs (different communication categories)
CATEGORIES = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]


def random_date_in_range(start_days_ago=90, end_days_ago=0):
    """Generate a random datetime within the last X days"""
    days_ago = random.randint(end_days_ago, start_days_ago)
    hours = random.randint(0, 23)
    minutes = random.randint(0, 59)
    seconds = random.randint(0, 59)
    
    date = datetime.now() - timedelta(days=days_ago, hours=hours, minutes=minutes, seconds=seconds)
    return date


def insert_realistic_data(num_records=2000):
    """Insert realistic dummy data for stock broker communications"""
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    print(f"🔄 Inserting {num_records} realistic records...")
    
    for i in range(num_records):
        # Generate realistic values
        ref_app_id = i
        ref_vendor_id = random.choice(VENDOR_IDS)
        receiver = random.choice(CLIENTS)
        sender = random.choice(SENDERS)
        
        # CC/BCC - sometimes empty, sometimes has values
        cc_data = random.choice([None, "manager@anandrathi.com", "compliance@anandrathi.com", ""])
        bcc_data = random.choice([None, "audit@anandrathi.com", ""])
        
        # Realistic dates (spread over last 3 months)
        submit_date = random_date_in_range(start_days_ago=90, end_days_ago=0)
        
        # Updated date is always after submit date
        updated_date = submit_date + timedelta(
            hours=random.randint(0, 48),
            minutes=random.randint(0, 59)
        )
        
        attachment_info = random.choice(ATTACHMENTS)
        request_data = random.choice(REQUEST_TEMPLATES)
        tracking_id = f"TRACK-{uuid.uuid4()}"
        gu_id = str(uuid.uuid4())
        
        # Realistic status distribution
        # 60% SENT, 20% FAILED, 10% PENDING, 10% others
        rand = random.random()
        if rand < 0.60:
            last_status = "SENT"
        elif rand < 0.80:
            last_status = "FAILED"
        elif rand < 0.90:
            last_status = "PENDING"
        else:
            last_status = random.choice(["CREATED", "SUBMITTED", "DELIVERED"])
        
        category_id = random.choice(CATEGORIES)
        
        # Insert query
        cursor.execute("""
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
        """, (
            ref_app_id,
            ref_vendor_id,
            receiver,
            sender,
            cc_data,
            bcc_data,
            submit_date,
            attachment_info,
            request_data,
            tracking_id,
            gu_id,
            last_status,
            updated_date,
            category_id
        ))
        
        # Progress indicator
        if (i + 1) % 200 == 0:
            print(f"  ✓ Inserted {i + 1}/{num_records} records...")
    
    conn.commit()
    cursor.close()
    conn.close()
    
    print(f"✅ Successfully inserted {num_records} realistic records!")
    print("\n📊 Data Distribution:")
    print("  • 50 different client emails")
    print("  • 10 different vendors")
    print("  • 6 different sender departments")
    print("  • 8 types of communications")
    print("  • Dates spread over last 90 days")
    print("  • ~60% SENT, ~20% FAILED, ~10% PENDING, ~10% others")


if __name__ == "__main__":
    # Clear existing data first (optional)
    choice = input("⚠️  Clear existing data before inserting? (y/n): ")
    
    if choice.lower() == 'y':
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM CommunicationsRequestStatus")
        conn.commit()
        cursor.close()
        conn.close()
        print("🗑️  Cleared existing data\n")
    
    # Insert new realistic data
    insert_realistic_data(num_records=1000)