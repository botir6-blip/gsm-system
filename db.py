import os
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_connection():
    return psycopg2.connect(DATABASE_URL, sslmode="require")


def fetch_all(query, params=None):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(query, params or ())
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def fetch_one(query, params=None):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
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


def column_exists(table_name, column_name):
    row = fetch_one("""
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
    """, (table_name, column_name))
    return row is not None


def ensure_column(table_name, column_name, ddl_sql):
    if not column_exists(table_name, column_name):
        execute_query(ddl_sql)


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    # ===== Fuel stations =====
    cur.execute("""
        CREATE TABLE IF NOT EXISTS fuel_stations (
            id SERIAL PRIMARY KEY,
            name VARCHAR(150) NOT NULL,
            company_id INTEGER NOT NULL,
            operator_user_id INTEGER,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ===== Fuel requests =====
    cur.execute("""
        CREATE TABLE IF NOT EXISTS fuel_requests (
            id SERIAL PRIMARY KEY,
            requester_user_id INTEGER NOT NULL,
            requester_company_id INTEGER,
            vehicle_id INTEGER,
            object_id INTEGER,
            project_name VARCHAR(150),
            requested_liters NUMERIC(12,2),
            approved_liters NUMERIC(12,2),
            fueled_liters NUMERIC(12,2),
            fuel_provider_company_id INTEGER,
            fuel_station_id INTEGER,
            status VARCHAR(30) DEFAULT 'new',
            comment TEXT,
            approved_by_user_id INTEGER,
            approved_at TIMESTAMP,
            fueled_by_user_id INTEGER,
            fueled_at TIMESTAMP,
            driver_confirmed_by_user_id INTEGER,
            driver_confirmed_at TIMESTAMP,
            dispatcher_checked_by_user_id INTEGER,
            dispatcher_checked_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    cur.close()
    conn.close()

    # ===== Safe ALTERs =====
    ensure_column(
        "fuel_requests",
        "requester_company_id",
        "ALTER TABLE fuel_requests ADD COLUMN requester_company_id INTEGER"
    )
    ensure_column(
        "fuel_requests",
        "fuel_provider_company_id",
        "ALTER TABLE fuel_requests ADD COLUMN fuel_provider_company_id INTEGER"
    )
    ensure_column(
        "fuel_requests",
        "fuel_station_id",
        "ALTER TABLE fuel_requests ADD COLUMN fuel_station_id INTEGER"
    )
    ensure_column(
        "fuel_requests",
        "approved_by_user_id",
        "ALTER TABLE fuel_requests ADD COLUMN approved_by_user_id INTEGER"
    )
    ensure_column(
        "fuel_requests",
        "approved_at",
        "ALTER TABLE fuel_requests ADD COLUMN approved_at TIMESTAMP"
    )
    ensure_column(
        "fuel_requests",
        "approved_liters",
        "ALTER TABLE fuel_requests ADD COLUMN approved_liters NUMERIC(12,2)"
    )
    ensure_column(
        "fuel_requests",
        "fueled_liters",
        "ALTER TABLE fuel_requests ADD COLUMN fueled_liters NUMERIC(12,2)"
    )
    ensure_column(
        "fuel_requests",
        "fueled_by_user_id",
        "ALTER TABLE fuel_requests ADD COLUMN fueled_by_user_id INTEGER"
    )
    ensure_column(
        "fuel_requests",
        "fueled_at",
        "ALTER TABLE fuel_requests ADD COLUMN fueled_at TIMESTAMP"
    )
    ensure_column(
        "fuel_requests",
        "driver_confirmed_by_user_id",
        "ALTER TABLE fuel_requests ADD COLUMN driver_confirmed_by_user_id INTEGER"
    )
    ensure_column(
        "fuel_requests",
        "driver_confirmed_at",
        "ALTER TABLE fuel_requests ADD COLUMN driver_confirmed_at TIMESTAMP"
    )
    ensure_column(
        "fuel_requests",
        "dispatcher_checked_by_user_id",
        "ALTER TABLE fuel_requests ADD COLUMN dispatcher_checked_by_user_id INTEGER"
    )
    ensure_column(
        "fuel_requests",
        "dispatcher_checked_at",
        "ALTER TABLE fuel_requests ADD COLUMN dispatcher_checked_at TIMESTAMP"
    )
