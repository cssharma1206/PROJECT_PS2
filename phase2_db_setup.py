"""
===============================================================================
PHASE 2 - DATABASE SETUP SCRIPT
Anand Rathi Communications Intelligence Platform
===============================================================================

This script creates the Phase 2 database tables in the SAME SQL Server instance
(GLADIATOR\SQLEXPRESS) and SAME database (anandrathi).

TABLES CREATED:
  1. Roles       - Role definitions & permissions (replaces hardcoded roles)
  2. Users_v2    - New user table with proper FK to Roles (Phase 2 auth)
  3. Token       - JWT refresh token storage
  4. QueryLog    - Tracks every NLQ query with generated SQL
  5. ErrorLog    - Application error tracking

EXISTING TABLES (NOT TOUCHED):
  - Users                          (Phase 1 - kept for backward compatibility)
  - CommunicationsRequestStatus    (Main data - 1000 rows, our query target)
  - AccessLog                      (Phase 1 audit log)

RUN THIS SCRIPT ONCE:
  python phase2_db_setup.py

===============================================================================
"""

import pyodbc
import bcrypt
from datetime import datetime


# ═══════════════════════════════════════════════════════════════════════════════
# DATABASE CONNECTION
# ═══════════════════════════════════════════════════════════════════════════════
def get_connection():
    """Connect to the existing anandrathi database on GLADIATOR\SQLEXPRESS"""
    return pyodbc.connect(
        "DRIVER={ODBC Driver 17 for SQL Server};"
        "SERVER=GLADIATOR\\SQLEXPRESS;"
        "DATABASE=anandrathi;"
        "Trusted_Connection=yes;"
    )


def hash_password(password):
    """Hash password using bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


# ═══════════════════════════════════════════════════════════════════════════════
# TABLE 1: ROLES (Rules/Permissions)
# ═══════════════════════════════════════════════════════════════════════════════
CREATE_ROLES_TABLE = """
IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='Roles' AND xtype='U')
BEGIN
    CREATE TABLE Roles (
        role_id             INT PRIMARY KEY IDENTITY(1,1),
        role_name           NVARCHAR(50) NOT NULL UNIQUE,
        can_query           BIT DEFAULT 1,
        can_export          BIT DEFAULT 0,
        can_admin           BIT DEFAULT 0,
        can_register_db     BIT DEFAULT 0,
        app_code            NVARCHAR(50) NULL,
        application_id      INT NULL,
        description         NVARCHAR(500) NULL,
        created_at          DATETIME DEFAULT GETDATE()
    );
    PRINT '  [+] Roles table CREATED';
END
ELSE
    PRINT '  [=] Roles table already exists';
"""

# ═══════════════════════════════════════════════════════════════════════════════
# TABLE 2: USERS_V2 (Phase 2 User Management)
# ═══════════════════════════════════════════════════════════════════════════════
CREATE_USERS_V2_TABLE = """
IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='Users_v2' AND xtype='U')
BEGIN
    CREATE TABLE Users_v2 (
        user_id             INT PRIMARY KEY IDENTITY(1,1),
        username            NVARCHAR(100) NOT NULL UNIQUE,
        password_hash       NVARCHAR(255) NOT NULL,
        email               NVARCHAR(200) NOT NULL,
        full_name           NVARCHAR(200) NOT NULL,
        role_id             INT NOT NULL,
        is_active           BIT DEFAULT 1,
        created_at          DATETIME DEFAULT GETDATE(),
        last_login          DATETIME NULL,
        CONSTRAINT FK_Users_v2_Roles FOREIGN KEY (role_id) REFERENCES Roles(role_id)
    );
    PRINT '  [+] Users_v2 table CREATED';
END
ELSE
    PRINT '  [=] Users_v2 table already exists';
"""

# ═══════════════════════════════════════════════════════════════════════════════
# TABLE 3: TOKEN (JWT Refresh Token Storage)
# ═══════════════════════════════════════════════════════════════════════════════
CREATE_TOKEN_TABLE = """
IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='Token' AND xtype='U')
BEGIN
    CREATE TABLE Token (
        token_id            INT PRIMARY KEY IDENTITY(1,1),
        user_id             INT NOT NULL,
        token_hash          NVARCHAR(500) NOT NULL,
        token_type          NVARCHAR(20) DEFAULT 'refresh',
        expires_at          DATETIME NOT NULL,
        is_revoked          BIT DEFAULT 0,
        created_at          DATETIME DEFAULT GETDATE(),
        ip_address          NVARCHAR(50) NULL,
        CONSTRAINT FK_Token_Users FOREIGN KEY (user_id) REFERENCES Users_v2(user_id)
    );
    PRINT '  [+] Token table CREATED';
END
ELSE
    PRINT '  [=] Token table already exists';
"""

# ═══════════════════════════════════════════════════════════════════════════════
# TABLE 4: QUERYLOG (Track Every NLQ Query)
# ═══════════════════════════════════════════════════════════════════════════════
CREATE_QUERYLOG_TABLE = """
IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='QueryLog' AND xtype='U')
BEGIN
    CREATE TABLE QueryLog (
        log_id              INT PRIMARY KEY IDENTITY(1,1),
        user_id             INT NOT NULL,
        query_text          NVARCHAR(MAX) NOT NULL,
        generated_sql       NVARCHAR(MAX) NULL,
        mcp_response        NVARCHAR(MAX) NULL,
        execution_time_ms   INT NULL,
        result_count        INT DEFAULT 0,
        was_successful      BIT DEFAULT 1,
        method              NVARCHAR(50) NULL,
        created_at          DATETIME DEFAULT GETDATE(),
        CONSTRAINT FK_QueryLog_Users FOREIGN KEY (user_id) REFERENCES Users_v2(user_id)
    );
    PRINT '  [+] QueryLog table CREATED';
END
ELSE
    PRINT '  [=] QueryLog table already exists';
"""

# ═══════════════════════════════════════════════════════════════════════════════
# TABLE 5: ERRORLOG (Application Error Tracking)
# ═══════════════════════════════════════════════════════════════════════════════
CREATE_ERRORLOG_TABLE = """
IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='ErrorLog' AND xtype='U')
BEGIN
    CREATE TABLE ErrorLog (
        error_id            INT PRIMARY KEY IDENTITY(1,1),
        user_id             INT NULL,
        error_type          NVARCHAR(100) NOT NULL,
        error_message       NVARCHAR(MAX) NOT NULL,
        endpoint            NVARCHAR(200) NULL,
        request_body        NVARCHAR(MAX) NULL,
        stack_trace         NVARCHAR(MAX) NULL,
        created_at          DATETIME DEFAULT GETDATE()
    );
    PRINT '  [+] ErrorLog table CREATED';
END
ELSE
    PRINT '  [=] ErrorLog table already exists';
"""


# ═══════════════════════════════════════════════════════════════════════════════
# SEED DATA: Default Roles
# ═══════════════════════════════════════════════════════════════════════════════
SEED_ROLES = [
    # (role_name, can_query, can_export, can_admin, can_register_db, app_code, application_id, description)
    ('Admin',    1, 1, 1, 1, None, None,  'Full system administrator. Access to all data, all databases, user management, and logs.'),
    ('RM_Head',  1, 1, 0, 0, 'APP01', 10, 'Relationship Manager Head. Can query and export team data for ApplicationId 10 (Vendors 1-7).'),
    ('RM',       1, 0, 0, 0, 'APP01', 10, 'Relationship Manager. Can query team data for ApplicationId 10. No export permission.'),
    ('RM_Head2', 1, 1, 0, 0, 'APP01', 20, 'RM Head for Team 20. Can query and export data for ApplicationId 20 (Vendors 8-14).'),
    ('RM2',      1, 0, 0, 0, 'APP01', 20, 'RM for Team 20. Can query data for ApplicationId 20. No export permission.'),
    ('RM3',      1, 0, 0, 0, 'APP01', 15, 'RM for Team 15. Can query data for ApplicationId 15 (Vendors 15-30).'),
    ('Client',   1, 0, 0, 0, 'APP01', None, 'Client user. Can only see their own communication data.'),
]


# ═══════════════════════════════════════════════════════════════════════════════
# SEED DATA: Default Users (migrated from Phase 1 + new ones)
# ═══════════════════════════════════════════════════════════════════════════════
SEED_USERS = [
    # (username, password, email, full_name, role_name)
    ('admin',      'admin123',   'admin@anandrathi.com',           'System Administrator',  'Admin'),
    ('superadmin', 'super123',   'superadmin@anandrathi.com',      'Super Administrator',   'Admin'),
    ('rmhead1',    'head123',    'rajesh.sharma@anandrathi.com',   'Rajesh Kumar Sharma',   'RM_Head'),
    ('rm1',        'rm123',      'priya.verma@anandrathi.com',     'Priya Verma',           'RM'),
    ('rm2',        'rm123',      'amit.singh@anandrathi.com',      'Amit Singh',            'RM'),
    ('rmhead2',    'head456',    'priya.desai@anandrathi.com',     'Priya Desai',           'RM_Head2'),
    ('rm3',        'rm123',      'vikram.singh@anandrathi.com',    'Vikram Singh',          'RM2'),
    ('rm4',        'rm123',      'anjali.mehta@anandrathi.com',    'Anjali Mehta',          'RM2'),
    ('rm5',        'rm123',      'rahul.kumar@anandrathi.com',     'Rahul Kumar',           'RM3'),
    ('client1',    'client123',  'rahul.gupta@gmail.com',          'Rahul Gupta',           'Client'),
    ('client2',    'client123',  'meera.nair@yahoo.com',           'Meera Nair',            'Client'),
    ('client3',    'client123',  'suresh.pillai@gmail.com',        'Suresh Pillai',         'Client'),
]


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN SETUP FUNCTION
# ═══════════════════════════════════════════════════════════════════════════════
def setup_phase2_database():
    print("=" * 70)
    print("  ANAND RATHI - PHASE 2 DATABASE SETUP")
    print("  Communications Intelligence Platform")
    print("  Server: GLADIATOR\\SQLEXPRESS | Database: anandrathi")
    print("=" * 70)

    conn = get_connection()
    cursor = conn.cursor()

    # ─── Step 1: Create Tables ───────────────────────────────────────────
    print("\n[STEP 1/5] Creating Tables...")
    print("-" * 50)

    for name, sql in [
        ("Roles",    CREATE_ROLES_TABLE),
        ("Users_v2", CREATE_USERS_V2_TABLE),
        ("Token",    CREATE_TOKEN_TABLE),
        ("QueryLog", CREATE_QUERYLOG_TABLE),
        ("ErrorLog", CREATE_ERRORLOG_TABLE),
    ]:
        try:
            cursor.execute(sql)
            conn.commit()
        except Exception as e:
            print(f"  [!] Error creating {name}: {e}")

    # ─── Step 2: Seed Roles ──────────────────────────────────────────────
    print("\n[STEP 2/5] Seeding Roles...")
    print("-" * 50)

    roles_added = 0
    for role_name, can_q, can_e, can_a, can_r, app_code, app_id, desc in SEED_ROLES:
        try:
            cursor.execute("SELECT COUNT(*) FROM Roles WHERE role_name = ?", (role_name,))
            if cursor.fetchone()[0] == 0:
                cursor.execute("""
                    INSERT INTO Roles (role_name, can_query, can_export, can_admin, 
                                       can_register_db, app_code, application_id, description)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (role_name, can_q, can_e, can_a, can_r, app_code, app_id, desc))
                roles_added += 1
                print(f"  [+] Added role: {role_name}")
            else:
                print(f"  [=] Role already exists: {role_name}")
        except Exception as e:
            print(f"  [!] Error adding role {role_name}: {e}")
    conn.commit()
    print(f"  Total new roles added: {roles_added}")

    # ─── Step 3: Seed Users ──────────────────────────────────────────────
    print("\n[STEP 3/5] Seeding Users...")
    print("-" * 50)

    users_added = 0
    for username, password, email, full_name, role_name in SEED_USERS:
        try:
            cursor.execute("SELECT COUNT(*) FROM Users_v2 WHERE username = ?", (username,))
            if cursor.fetchone()[0] == 0:
                # Look up role_id
                cursor.execute("SELECT role_id FROM Roles WHERE role_name = ?", (role_name,))
                role_row = cursor.fetchone()
                if not role_row:
                    print(f"  [!] Role '{role_name}' not found for user '{username}'. Skipping.")
                    continue
                role_id = role_row[0]

                pwd_hash = hash_password(password)
                cursor.execute("""
                    INSERT INTO Users_v2 (username, password_hash, email, full_name, role_id)
                    VALUES (?, ?, ?, ?, ?)
                """, (username, pwd_hash, email, full_name, role_id))
                users_added += 1
                print(f"  [+] Added user: {username} (role: {role_name})")
            else:
                print(f"  [=] User already exists: {username}")
        except Exception as e:
            print(f"  [!] Error adding user {username}: {e}")
    conn.commit()
    print(f"  Total new users added: {users_added}")

    # ─── Step 4: Verify Existing Data ────────────────────────────────────
    print("\n[STEP 4/5] Verifying Existing Data...")
    print("-" * 50)

    try:
        cursor.execute("SELECT COUNT(*) FROM CommunicationsRequestStatus")
        comm_count = cursor.fetchone()[0]
        print(f"  CommunicationsRequestStatus: {comm_count} rows (existing data)")
    except:
        print("  [!] CommunicationsRequestStatus table not found!")

    try:
        cursor.execute("SELECT COUNT(*) FROM AccessLog")
        access_count = cursor.fetchone()[0]
        print(f"  AccessLog (Phase 1): {access_count} rows")
    except:
        print("  [=] AccessLog table not found (Phase 1 may not have run)")

    try:
        cursor.execute("SELECT COUNT(*) FROM Users")
        old_users = cursor.fetchone()[0]
        print(f"  Users (Phase 1 - legacy): {old_users} rows (kept for reference)")
    except:
        print("  [=] Old Users table not found")

    # ─── Step 5: Summary ─────────────────────────────────────────────────
    print("\n[STEP 5/5] Phase 2 Tables Summary...")
    print("-" * 50)

    for table in ['Roles', 'Users_v2', 'Token', 'QueryLog', 'ErrorLog']:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"  {table}: {count} rows")
        except Exception as e:
            print(f"  {table}: ERROR - {e}")

    print("\n  Roles breakdown:")
    try:
        cursor.execute("SELECT role_name, application_id, can_query, can_export, can_admin FROM Roles ORDER BY role_id")
        for row in cursor.fetchall():
            perms = []
            if row[2]: perms.append("query")
            if row[3]: perms.append("export")
            if row[4]: perms.append("admin")
            app = f"AppId={row[1]}" if row[1] else "All"
            print(f"    {row[0]:12s} | {app:10s} | permissions: {', '.join(perms)}")
    except Exception as e:
        print(f"    Error: {e}")

    print("\n  Users breakdown:")
    try:
        cursor.execute("""
            SELECT u.username, u.full_name, r.role_name, u.email
            FROM Users_v2 u
            JOIN Roles r ON u.role_id = r.role_id
            ORDER BY r.role_id, u.user_id
        """)
        for row in cursor.fetchall():
            print(f"    {row[0]:12s} | {row[1]:25s} | {row[2]:10s} | {row[3]}")
    except Exception as e:
        print(f"    Error: {e}")

    # ─── Done ────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("  PHASE 2 DATABASE SETUP COMPLETE!")
    print("=" * 70)
    print(f"\n  Server:   GLADIATOR\\SQLEXPRESS")
    print(f"  Database: anandrathi")
    print(f"  Tables created: Roles, Users_v2, Token, QueryLog, ErrorLog")
    print(f"  Existing tables: CommunicationsRequestStatus, Users, AccessLog")
    print(f"\n  Login Credentials (Phase 2):")
    print(f"    Admins:    admin/admin123, superadmin/super123")
    print(f"    RM Heads:  rmhead1/head123, rmhead2/head456")
    print(f"    RMs:       rm1/rm123, rm2/rm123, rm3/rm123, rm4/rm123, rm5/rm123")
    print(f"    Clients:   client1/client123, client2/client123, client3/client123")
    print(f"\n  Next step: Run the FastAPI server (Day 4)")
    print("=" * 70)

    cursor.close()
    conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# GENERATE TOML SCHEMA (For feeding to AI/MCP - reduces token usage)
# ═══════════════════════════════════════════════════════════════════════════════
def generate_schema_toml():
    """
    Generates a TOML representation of the database schema.
    This is what your mentor Aman mentioned - feed this to the AI
    instead of raw SQL definitions. It uses fewer tokens.
    """
    toml_content = '''# ═══════════════════════════════════════════════════════════
# ANAND RATHI - DATABASE SCHEMA (TOML Format)
# For AI/MCP consumption - reduces token usage
# Database: anandrathi on GLADIATOR\\SQLEXPRESS
# ═══════════════════════════════════════════════════════════

[database]
name = "anandrathi"
server = "GLADIATOR\\\\SQLEXPRESS"
type = "mssql"

# ─── MAIN DATA TABLE (Query Target) ──────────────────────
[tables.CommunicationsRequestStatus]
description = "Email/SMS communication records for Anand Rathi clients. 1000 rows."
primary_key = "Id"
row_count = 1000

[tables.CommunicationsRequestStatus.columns]
Id = { type = "int", description = "Unique record ID", example = "2006" }
ReferenceVendorId = { type = "int", description = "Email service provider ID", example = "1, 7, 15, 30", alias = ["vendor", "vendor id", "provider"] }
ReferenceApplicationId = { type = "int", description = "Team assignment for access control", example = "10, 15, 20", alias = ["team", "application", "app id"] }
Receiver = { type = "nvarchar", description = "Client email address (recipient)", example = "client1@gmail.com", alias = ["to", "recipient", "client email", "sent to"] }
Sender = { type = "nvarchar", description = "Anand Rathi sender email", example = "trading@anandrathi.com", alias = ["from", "sender email", "sent by"] }
CCData = { type = "nvarchar", description = "CC email addresses", example = "compliance@anandrathi.com", alias = ["cc", "copy"] }
BccData = { type = "nvarchar", description = "BCC email addresses", alias = ["bcc", "blind copy"] }
SubmitDate = { type = "datetime", description = "When email was submitted", example = "2026-01-15 10:30:00", alias = ["date", "sent date", "when", "submit date"] }
LastStatus = { type = "nvarchar", description = "Current status of email", example = "SENT, FAILED, PENDING, CREATED, SUBMITTED, DELIVERED", alias = ["status", "email status"] }
AttachmentInfo = { type = "nvarchar", description = "Attachment filename", example = "account_opening_form.pdf", alias = ["attachment", "document", "file"] }
CategoryId = { type = "int", description = "Category identifier", example = "1-10", alias = ["category"] }
UpdatedDate = { type = "datetime", description = "Last update timestamp", alias = ["updated", "last updated"] }

[tables.CommunicationsRequestStatus.access_control]
field = "ReferenceApplicationId"
note = "Non-admin users must filter by their application_id from Roles table"

# ─── PLATFORM TABLES ─────────────────────────────────────
[tables.Users_v2]
description = "Platform users for Phase 2 authentication"
primary_key = "user_id"

[tables.Roles]
description = "Role definitions with permissions and app_code mapping"
primary_key = "role_id"

[tables.Token]
description = "JWT refresh token storage"
primary_key = "token_id"

[tables.QueryLog]
description = "Tracks every natural language query and AI-generated SQL"
primary_key = "log_id"

[tables.ErrorLog]
description = "Application error tracking"
primary_key = "error_id"
'''
    return toml_content


# ═══════════════════════════════════════════════════════════════════════════════
# RAW SQL STATEMENTS (If you want to run directly in SSMS)
# ═══════════════════════════════════════════════════════════════════════════════
def print_raw_sql():
    """Print all CREATE TABLE statements for manual execution in SSMS"""
    print("\n" + "=" * 70)
    print("  RAW SQL - Copy and paste into SQL Server Management Studio")
    print("=" * 70)
    
    raw_sql = """
-- ═══════════════════════════════════════════════════════════════════
-- PHASE 2: DATABASE TABLES
-- Run on: GLADIATOR\\SQLEXPRESS > anandrathi database
-- ═══════════════════════════════════════════════════════════════════

-- TABLE 1: Roles (Permissions & Access Control)
IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='Roles' AND xtype='U')
CREATE TABLE Roles (
    role_id             INT PRIMARY KEY IDENTITY(1,1),
    role_name           NVARCHAR(50) NOT NULL UNIQUE,
    can_query           BIT DEFAULT 1,
    can_export          BIT DEFAULT 0,
    can_admin           BIT DEFAULT 0,
    can_register_db     BIT DEFAULT 0,
    app_code            NVARCHAR(50) NULL,
    application_id      INT NULL,
    description         NVARCHAR(500) NULL,
    created_at          DATETIME DEFAULT GETDATE()
);
GO

-- TABLE 2: Users_v2 (Phase 2 Authentication)
IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='Users_v2' AND xtype='U')
CREATE TABLE Users_v2 (
    user_id             INT PRIMARY KEY IDENTITY(1,1),
    username            NVARCHAR(100) NOT NULL UNIQUE,
    password_hash       NVARCHAR(255) NOT NULL,
    email               NVARCHAR(200) NOT NULL,
    full_name           NVARCHAR(200) NOT NULL,
    role_id             INT NOT NULL,
    is_active           BIT DEFAULT 1,
    created_at          DATETIME DEFAULT GETDATE(),
    last_login          DATETIME NULL,
    CONSTRAINT FK_Users_v2_Roles FOREIGN KEY (role_id) REFERENCES Roles(role_id)
);
GO

-- TABLE 3: Token (JWT Refresh Token Storage)
IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='Token' AND xtype='U')
CREATE TABLE Token (
    token_id            INT PRIMARY KEY IDENTITY(1,1),
    user_id             INT NOT NULL,
    token_hash          NVARCHAR(500) NOT NULL,
    token_type          NVARCHAR(20) DEFAULT 'refresh',
    expires_at          DATETIME NOT NULL,
    is_revoked          BIT DEFAULT 0,
    created_at          DATETIME DEFAULT GETDATE(),
    ip_address          NVARCHAR(50) NULL,
    CONSTRAINT FK_Token_Users FOREIGN KEY (user_id) REFERENCES Users_v2(user_id)
);
GO

-- TABLE 4: QueryLog (NLQ Query Tracking)
IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='QueryLog' AND xtype='U')
CREATE TABLE QueryLog (
    log_id              INT PRIMARY KEY IDENTITY(1,1),
    user_id             INT NOT NULL,
    query_text          NVARCHAR(MAX) NOT NULL,
    generated_sql       NVARCHAR(MAX) NULL,
    mcp_response        NVARCHAR(MAX) NULL,
    execution_time_ms   INT NULL,
    result_count        INT DEFAULT 0,
    was_successful      BIT DEFAULT 1,
    method              NVARCHAR(50) NULL,
    created_at          DATETIME DEFAULT GETDATE(),
    CONSTRAINT FK_QueryLog_Users FOREIGN KEY (user_id) REFERENCES Users_v2(user_id)
);
GO

-- TABLE 5: ErrorLog (Application Error Tracking)
IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='ErrorLog' AND xtype='U')
CREATE TABLE ErrorLog (
    error_id            INT PRIMARY KEY IDENTITY(1,1),
    user_id             INT NULL,
    error_type          NVARCHAR(100) NOT NULL,
    error_message       NVARCHAR(MAX) NOT NULL,
    endpoint            NVARCHAR(200) NULL,
    request_body        NVARCHAR(MAX) NULL,
    stack_trace         NVARCHAR(MAX) NULL,
    created_at          DATETIME DEFAULT GETDATE()
);
GO

-- ═══════════════════════════════════════════════════════════════════
-- SEED DATA: Roles
-- ═══════════════════════════════════════════════════════════════════
INSERT INTO Roles (role_name, can_query, can_export, can_admin, can_register_db, app_code, application_id, description) VALUES
('Admin',    1, 1, 1, 1, NULL,   NULL, 'Full system administrator'),
('RM_Head',  1, 1, 0, 0, 'APP01', 10,  'RM Head - Team 10 (Vendors 1-7)'),
('RM',       1, 0, 0, 0, 'APP01', 10,  'RM - Team 10'),
('RM_Head2', 1, 1, 0, 0, 'APP01', 20,  'RM Head - Team 20 (Vendors 8-14)'),
('RM2',      1, 0, 0, 0, 'APP01', 20,  'RM - Team 20'),
('RM3',      1, 0, 0, 0, 'APP01', 15,  'RM - Team 15 (Vendors 15-30)'),
('Client',   1, 0, 0, 0, 'APP01', NULL, 'Client - own data only');
GO

-- ═══════════════════════════════════════════════════════════════════
-- VERIFY
-- ═══════════════════════════════════════════════════════════════════
SELECT 'Roles' AS TableName, COUNT(*) AS Rows FROM Roles
UNION ALL SELECT 'Users_v2', COUNT(*) FROM Users_v2
UNION ALL SELECT 'Token', COUNT(*) FROM Token
UNION ALL SELECT 'QueryLog', COUNT(*) FROM QueryLog
UNION ALL SELECT 'ErrorLog', COUNT(*) FROM ErrorLog
UNION ALL SELECT 'CommunicationsRequestStatus', COUNT(*) FROM CommunicationsRequestStatus;
GO
"""
    print(raw_sql)


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--sql":
        print_raw_sql()
    elif len(sys.argv) > 1 and sys.argv[1] == "--toml":
        print(generate_schema_toml())
    else:
        setup_phase2_database()
        
        # Also save the TOML schema file
        toml = generate_schema_toml()
        with open("schema.toml", "w", encoding="utf-8") as f:
            f.write(toml)
        print(f"\n  Schema TOML saved to: schema.toml")
        print(f"  (Feed this to AI/MCP for schema-aware query generation)")