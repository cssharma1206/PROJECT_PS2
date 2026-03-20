import pyodbc

def get_db_connection():
    return pyodbc.connect(
        "DRIVER={ODBC Driver 17 for SQL Server};"
        "SERVER=GLADIATOR\\SQLEXPRESS;"
        "DATABASE=anandrathi;"
        "Trusted_Connection=yes;"
    )
