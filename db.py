import os
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_connection():
    return psycopg2.connect(
        DATABASE_URL,
        sslmode="require"
    )


def fetch_all(query, params=None):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(query, params or ())
        rows = cur.fetchall()
        return rows
    finally:
        cur.close()
        conn.close()


def fetch_one(query, params=None):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(query, params or ())
        row = cur.fetchone()
        return row
    finally:
        cur.close()
        conn.close()


def execute_query(query, params=None):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(query, params or ())
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def column_exists(table_name, column_name):
    row = fetch_one("""
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
    """, (table_name, column_name))
    return row is not None


def table_exists(table_name):
    row = fetch_one("""
        SELECT 1
        FROM information_schema.tables
        WHERE table_name = %s
    """, (table_name,))
    return row is not None


def ensure_column(table_name, column_name, ddl_sql):
    if not column_exists(table_name, column_name):
        execute_query(ddl_sql)


def ensure_users_columns():
    if not table_exists("users"):
        return

    ensure_column(
        "users",
        "full_name",
        "ALTER TABLE users ADD COLUMN full_name VARCHAR(150)"
    )
    ensure_column(
        "users",
        "role",
        "ALTER TABLE users ADD COLUMN role VARCHAR(50) DEFAULT 'user'"
    )
    ensure_column(
        "users",
        "company_id",
        "ALTER TABLE users ADD COLUMN company_id INTEGER"
    )
    ensure_column(
        "users",
        "is_active",
        "ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT TRUE"
    )
    ensure_column(
        "users",
        "created_at",
        "ALTER TABLE users ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
    )


def ensure_companies_columns():
    if not table_exists("companies"):
        return

    ensure_column(
        "companies",
        "name",
        "ALTER TABLE companies ADD COLUMN name VARCHAR(150)"
    )
    ensure_column(
        "companies",
        "is_active",
        "ALTER TABLE companies ADD COLUMN is_active BOOLEAN DEFAULT TRUE"
    )
    ensure_column(
        "companies",
        "created_at",
        "ALTER TABLE companies ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
    )


def ensure_objects_columns():
    if not table_exists("objects"):
        return

    ensure_column(
        "objects",
        "name",
        "ALTER TABLE objects ADD COLUMN name VARCHAR(150)"
    )
    ensure_column(
        "objects",
        "company_id",
        "ALTER TABLE objects ADD COLUMN company_id INTEGER"
    )
    ensure_column(
        "objects",
        "is_active",
        "ALTER TABLE objects ADD COLUMN is_active BOOLEAN DEFAULT TRUE"
    )
    ensure_column(
        "objects",
        "created_at",
        "ALTER TABLE objects ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
    )


def ensure_vehicles_columns():
    if not table_exists("vehicles"):
        return

    ensure_column(
        "vehicles",
        "brand",
        "ALTER TABLE vehicles ADD COLUMN brand VARCHAR(100)"
    )
    ensure_column(
        "vehicles",
        "vehicle_type",
        "ALTER TABLE vehicles ADD COLUMN vehicle_type VARCHAR(100)"
    )
    ensure_column(
        "vehicles",
        "license_plate",
        "ALTER TABLE vehicles ADD COLUMN license_plate VARCHAR(50)"
    )
    ensure_column(
        "vehicles",
        "company_id",
        "ALTER TABLE vehicles ADD COLUMN company_id INTEGER"
    )
    ensure_column(
        "vehicles",
        "is_active",
        "ALTER TABLE vehicles ADD COLUMN is_active BOOLEAN DEFAULT TRUE"
    )
    ensure_column(
        "vehicles",
        "created_at",
        "ALTER TABLE vehicles ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
    )


def ensure_fuel_stations_columns():
    if not table_exists("fuel_stations"):
        return

    ensure_column(
        "fuel_stations",
        "name",
        "ALTER TABLE fuel_stations ADD COLUMN name VARCHAR(150)"
    )
    ensure_column(
        "fuel_stations",
        "company_id",
        "ALTER TABLE fuel_stations ADD COLUMN company_id INTEGER"
    )
    ensure_column(
        "fuel_stations",
        "operator_user_id",
        "ALTER TABLE fuel_stations ADD COLUMN operator_user_id INTEGER"
    )
    ensure_column(
        "fuel_stations",
        "is_active",
        "ALTER TABLE fuel_stations ADD COLUMN is_active BOOLEAN DEFAULT TRUE"
    )
    ensure_column(
        "fuel_stations",
        "created_at",
        "ALTER TABLE fuel_stations ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
    )


def ensure_fuel_requests_columns():
    if not table_exists("fuel_requests"):
        return

    ensure_column(
        "fuel_requests",
        "requester_user_id",
        "ALTER TABLE fuel_requests ADD COLUMN requester_user_id INTEGER"
    )
    ensure_column(
        "fuel_requests",
        "requester_company_id",
        "ALTER TABLE fuel_requests ADD COLUMN requester_company_id INTEGER"
    )
    ensure_column(
        "fuel_requests",
        "vehicle_id",
        "ALTER TABLE fuel_requests ADD COLUMN vehicle_id INTEGER"
    )
    ensure_column(
        "fuel_requests",
        "object_id",
        "ALTER TABLE fuel_requests ADD COLUMN object_id INTEGER"
    )
    ensure_column(
        "fuel_requests",
        "project_name",
        "ALTER TABLE fuel_requests ADD COLUMN project_name VARCHAR(150)"
    )
    ensure_column(
        "fuel_requests",
        "requested_liters",
        "ALTER TABLE fuel_requests ADD COLUMN requested_liters NUMERIC(12,2)"
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
        "status",
        "ALTER TABLE fuel_requests ADD COLUMN status VARCHAR(30) DEFAULT 'new'"
    )
    ensure_column(
        "fuel_requests",
        "comment",
        "ALTER TABLE fuel_requests ADD COLUMN comment TEXT"
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
    ensure_column(
        "fuel_requests",
        "created_at",
        "ALTER TABLE fuel_requests ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
    )


def ensure_fuel_transactions_columns():
    if not table_exists("fuel_transactions"):
        return

    ensure_column(
        "fuel_transactions",
        "vehicle",
        "ALTER TABLE fuel_transactions ADD COLUMN vehicle VARCHAR(50)"
    )
    ensure_column(
        "fuel_transactions",
        "object_name",
        "ALTER TABLE fuel_transactions ADD COLUMN object_name VARCHAR(100)"
    )
    ensure_column(
        "fuel_transactions",
        "entry_type",
        "ALTER TABLE fuel_transactions ADD COLUMN entry_type VARCHAR(20)"
    )
    ensure_column(
        "fuel_transactions",
        "liters",
        "ALTER TABLE fuel_transactions ADD COLUMN liters NUMERIC"
    )
    ensure_column(
        "fuel_transactions",
        "odometer",
        "ALTER TABLE fuel_transactions ADD COLUMN odometer INTEGER"
    )
    ensure_column(
        "fuel_transactions",
        "entered_by",
        "ALTER TABLE fuel_transactions ADD COLUMN entered_by VARCHAR(100)"
    )
    ensure_column(
        "fuel_transactions",
        "driver_confirmed",
        "ALTER TABLE fuel_transactions ADD COLUMN driver_confirmed BOOLEAN DEFAULT FALSE"
    )
    ensure_column(
        "fuel_transactions",
        "dispatcher_status",
        "ALTER TABLE fuel_transactions ADD COLUMN dispatcher_status VARCHAR(20) DEFAULT 'new'"
    )
    ensure_column(
        "fuel_transactions",
        "comment",
        "ALTER TABLE fuel_transactions ADD COLUMN comment TEXT"
    )
    ensure_column(
        "fuel_transactions",
        "created_at",
        "ALTER TABLE fuel_transactions ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
    )


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS companies (
                id SERIAL PRIMARY KEY,
                name VARCHAR(150) NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(100),
                password VARCHAR(255),
                full_name VARCHAR(150),
                role VARCHAR(50) DEFAULT 'user',
                company_id INTEGER,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS objects (
                id SERIAL PRIMARY KEY,
                name VARCHAR(150) NOT NULL,
                company_id INTEGER,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS vehicles (
                id SERIAL PRIMARY KEY,
                brand VARCHAR(100),
                vehicle_type VARCHAR(100),
                license_plate VARCHAR(50),
                company_id INTEGER,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS fuel_stations (
                id SERIAL PRIMARY KEY,
                name VARCHAR(150) NOT NULL,
                company_id INTEGER,
                operator_user_id INTEGER,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS fuel_requests (
                id SERIAL PRIMARY KEY,
                requester_user_id INTEGER,
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

        cur.execute("""
            CREATE TABLE IF NOT EXISTS fuel_transactions (
                id SERIAL PRIMARY KEY,
                vehicle VARCHAR(50),
                object_name VARCHAR(100),
                entry_type VARCHAR(20),
                liters NUMERIC,
                odometer INTEGER,
                entered_by VARCHAR(100),
                driver_confirmed BOOLEAN DEFAULT FALSE,
                dispatcher_status VARCHAR(20) DEFAULT 'new',
                comment TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
    finally:
        cur.close()
        conn.close()

    ensure_users_columns()
    ensure_companies_columns()
    ensure_objects_columns()
    ensure_vehicles_columns()
    ensure_fuel_stations_columns()
    ensure_fuel_requests_columns()
    ensure_fuel_transactions_columns()
