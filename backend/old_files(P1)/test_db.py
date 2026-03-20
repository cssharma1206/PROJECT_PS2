from db.connection import get_db_connection

try:
    conn = get_db_connection()
    print("DB CONNECTED SUCCESSFULLY")
    conn.close()
except Exception as e:
    print("DB CONNECTION FAILED:", e)
