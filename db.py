import os
import psycopg
from psycopg.rows import dict_row
from werkzeug.security import generate_password_hash

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_connection():
    return psycopg.connect(
        DATABASE_URL,
        sslmode="require",
        row_factory=dict_row
    )


def normalize_plate(plate: str) -> str:
    if not plate:
        return ""
    return "".join(ch for ch in plate.upper() if ch.isalnum())


def fetch_all(query, params=None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(query, params or ())
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def fetch_one(query, params=None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(query, params or ())
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


def execute_query(query, params=None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(query, params or ())
    conn.commit()
    cur.close()
    conn.close()


def column_exists(cur, table_name, column_name):
    cur.execute("""
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
    """, (table_name, column_name))
    return cur.fetchone() is not None


def index_exists(cur, index_name):
    cur.execute("""
        SELECT 1
        FROM pg_indexes
        WHERE indexname = %s
    """, (index_name,))
    return cur.fetchone() is not None


def constraint_exists(cur, constraint_name):
    cur.execute("""
        SELECT 1
        FROM pg_constraint
        WHERE conname = %s
    """, (constraint_name,))
    return cur.fetchone() is not None


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS companies (
        id SERIAL PRIMARY KEY,
        name VARCHAR(150) NOT NULL UNIQUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        full_name VARCHAR(200) NOT NULL,
        username VARCHAR(100) NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        role VARCHAR(30) NOT NULL,
        company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
        position VARCHAR(200),
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()

    cur.execute("SELECT * FROM users WHERE username=%s", ("admin",))
    admin = cur.fetchone()

    if not admin:
        cur.execute("""
            INSERT INTO users (full_name, username, password_hash, role, is_active)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (username)
            DO UPDATE SET password_hash = EXCLUDED.password_hash
        """, (
            "Administrator",
            "admin",
            generate_password_hash("admin123"),
            "admin",
            True
        ))

    cur.execute("""
    CREATE TABLE IF NOT EXISTS objects (
        id SERIAL PRIMARY KEY,
        name VARCHAR(150) NOT NULL,
        company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS vehicles (
        id SERIAL PRIMARY KEY,
        brand VARCHAR(100) NOT NULL,
        vehicle_type VARCHAR(100) NOT NULL,
        plate_number VARCHAR(50) NOT NULL,
        plate_number_normalized VARCHAR(50),
        company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS fuel_requests (
        id SERIAL PRIMARY KEY,
        requester_company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
        object_id INTEGER REFERENCES objects(id) ON DELETE SET NULL,
        vehicle_id INTEGER REFERENCES vehicles(id) ON DELETE SET NULL,
        requested_by VARCHAR(100),
        requester_position VARCHAR(100),
        project_name VARCHAR(150),
        requested_liters NUMERIC(10,2) NOT NULL DEFAULT 0,
        approved_liters NUMERIC(10,2),
        actual_liters NUMERIC(10,2),
        fuel_supplier VARCHAR(150),
        speedometer INTEGER,
        approved_by VARCHAR(100),
        fueler_name VARCHAR(100),
        controller_name VARCHAR(100),
        request_comment TEXT,
        approval_comment TEXT,
        fueling_comment TEXT,
        control_comment TEXT,
        status VARCHAR(30) NOT NULL DEFAULT 'new',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        approved_at TIMESTAMP,
        fueled_at TIMESTAMP,
        checked_at TIMESTAMP
    )
    """)

    if not column_exists(cur, "fuel_requests", "approval_type"):
        cur.execute("""
            ALTER TABLE fuel_requests
            ADD COLUMN approval_type VARCHAR(20) NOT NULL DEFAULT 'internal'
        """)

    cur.execute("""
        UPDATE fuel_requests
        SET approval_type = 'internal'
        WHERE approval_type IS NULL
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS fuel_transactions (
        id SERIAL PRIMARY KEY,
        vehicle_id INTEGER REFERENCES vehicles(id) ON DELETE SET NULL,
        object_id INTEGER REFERENCES objects(id) ON DELETE SET NULL,
        entry_type VARCHAR(20) NOT NULL,
        liters NUMERIC(10,2) NOT NULL DEFAULT 0,
        speedometer INTEGER,
        entered_by VARCHAR(100),
        comment TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    transaction_columns = {
        "vehicle_id": "INTEGER REFERENCES vehicles(id) ON DELETE SET NULL",
        "object_id": "INTEGER REFERENCES objects(id) ON DELETE SET NULL",
        "entry_type": "VARCHAR(20) NOT NULL DEFAULT 'приход'",
        "liters": "NUMERIC(10,2) NOT NULL DEFAULT 0",
        "speedometer": "INTEGER",
        "entered_by": "VARCHAR(100)",
        "comment": "TEXT"
    }
    for col_name, col_type in transaction_columns.items():
        if not column_exists(cur, "fuel_transactions", col_name):
            cur.execute(f"ALTER TABLE fuel_transactions ADD COLUMN {col_name} {col_type}")

    if not column_exists(cur, "objects", "company_id"):
        cur.execute("""
            ALTER TABLE objects
            ADD COLUMN company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE
        """)

    if not column_exists(cur, "vehicles", "company_id"):
        cur.execute("""
            ALTER TABLE vehicles
            ADD COLUMN company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL
        """)

    if not column_exists(cur, "vehicles", "plate_number_normalized"):
        cur.execute("""
            ALTER TABLE vehicles
            ADD COLUMN plate_number_normalized VARCHAR(50)
        """)

    user_columns = {
        "company_id": "INTEGER REFERENCES companies(id) ON DELETE SET NULL",
        "is_active": "BOOLEAN NOT NULL DEFAULT TRUE",
        "position": "VARCHAR(200)"
    }
    for col_name, col_type in user_columns.items():
        if not column_exists(cur, "users", col_name):
            cur.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")

    if column_exists(cur, "users", "position"):
        cur.execute("""
            ALTER TABLE users
            ALTER COLUMN position TYPE VARCHAR(200)
        """)

    if column_exists(cur, "users", "full_name"):
        cur.execute("""
            ALTER TABLE users
            ALTER COLUMN full_name TYPE VARCHAR(200)
        """)

    request_columns = {
        "requester_company_id": "INTEGER REFERENCES companies(id) ON DELETE SET NULL",
        "object_id": "INTEGER REFERENCES objects(id) ON DELETE SET NULL",
        "vehicle_id": "INTEGER REFERENCES vehicles(id) ON DELETE SET NULL",
        "requested_by": "VARCHAR(100)",
        "requester_position": "VARCHAR(100)",
        "project_name": "VARCHAR(150)",
        "requested_liters": "NUMERIC(10,2) NOT NULL DEFAULT 0",
        "approved_liters": "NUMERIC(10,2)",
        "actual_liters": "NUMERIC(10,2)",
        "fuel_supplier": "VARCHAR(150)",
        "speedometer": "INTEGER",
        "approved_by": "VARCHAR(100)",
        "fueler_name": "VARCHAR(100)",
        "controller_name": "VARCHAR(100)",
        "request_comment": "TEXT",
        "approval_comment": "TEXT",
        "fueling_comment": "TEXT",
        "control_comment": "TEXT",
        "status": "VARCHAR(30) NOT NULL DEFAULT 'new'",
        "approved_at": "TIMESTAMP",
        "fueled_at": "TIMESTAMP",
        "checked_at": "TIMESTAMP",
    }
    for col_name, col_type in request_columns.items():
        if not column_exists(cur, "fuel_requests", col_name):
            cur.execute(f"ALTER TABLE fuel_requests ADD COLUMN {col_name} {col_type}")

    cur.execute("""
        SELECT id, plate_number
        FROM vehicles
        WHERE plate_number_normalized IS NULL OR plate_number_normalized = ''
    """)
    for row in cur.fetchall():
        cur.execute("""
            UPDATE vehicles
            SET plate_number_normalized = %s
            WHERE id = %s
        """, (normalize_plate(row["plate_number"]), row["id"]))

    if not index_exists(cur, "idx_vehicles_plate_number_normalized_unique"):
        cur.execute("""
            SELECT plate_number_normalized, COUNT(*)
            FROM vehicles
            WHERE plate_number_normalized IS NOT NULL
            GROUP BY plate_number_normalized
            HAVING COUNT(*) > 1
        """)
        duplicates = cur.fetchall()
        if not duplicates:
            cur.execute("""
                CREATE UNIQUE INDEX idx_vehicles_plate_number_normalized_unique
                ON vehicles (plate_number_normalized)
            """)

    if not constraint_exists(cur, "objects_name_company_unique"):
        cur.execute("""
            SELECT name, company_id, COUNT(*)
            FROM objects
            GROUP BY name, company_id
            HAVING COUNT(*) > 1
        """)
        duplicates = cur.fetchall()
        if not duplicates:
            cur.execute("""
                ALTER TABLE objects
                ADD CONSTRAINT objects_name_company_unique UNIQUE (name, company_id)
            """)

    conn.commit()
    cur.close()
    conn.close()
