from datetime import datetime
import uuid
from .connection import get_db_connection

def insert_dummy_data():
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

def execute_sql_query(sql: str):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(sql)

        if cursor.description is None:
            return []

        columns = [column[0] for column in cursor.description]
        rows = cursor.fetchall()

        return [dict(zip(columns, row)) for row in rows]

    finally:
        cursor.close()
        conn.close()
def execute_select(query: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(query)
    rows = cursor.fetchall()

    columns = [column[0] for column in cursor.description]
    results = [dict(zip(columns, row)) for row in rows]

    conn.close()
    return results


def get_last_failed():
    query = """
    SELECT TOP 5 *
    FROM CommunicationsRequestStatus
    WHERE LastStatus = 'FAILED'
    ORDER BY UpdatedDate DESC
    """
    return execute_select(query)

def get_last_by_status(status, limit=5):
    query = f"""
    SELECT TOP {limit} *
    FROM CommunicationsRequestStatus
    WHERE LastStatus = '{status}'
    ORDER BY UpdatedDate DESC
    """
    return execute_select(query)


def count_by_status(status):
    query = f"""
    SELECT COUNT(*) as count
    FROM CommunicationsRequestStatus
    WHERE LastStatus = '{status}'
    """
    return execute_select(query)
