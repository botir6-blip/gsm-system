import os
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash
from flask import g, has_request_context

DATABASE_URL = os.environ.get("DATABASE_URL")

ROLE_LABELS = {
    "fuel_operator": "Оператор ГСМ",
    "ats": "Проверяющий АТС",
    "viewer": "Только просмотр",
    "admin": "Администратор",
}

AUDIT_SUCCESS_LABELS = {
    True: "Успешно",
    False: "Ошибка",
}

ERIELL_DIVISIONS = ("ЭНГС", "ELAT", "Тампонаж")
DEFAULT_DENSITY = 0.84
WAREHOUSE_POINT_TYPES = ("WAREHOUSE", "TANK", "STORAGE")

POINT_TYPE_LABELS = {
    "WAREHOUSE": "ГСМ склад",
    "TANK": "ГСМ склад",
    "STORAGE": "ГСМ склад",
    "AZS": "АЗС",
    "PAZS": "ПАЗС",
    "BRIGADE": "Бригада",
    "EXTERNAL_OBJECT": "Внешний объект",
}


def _create_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def get_connection():
    if has_request_context():
        conn = getattr(g, "_db_conn", None)
        if conn is None or getattr(conn, "closed", 1):
            conn = _create_connection()
            g._db_conn = conn
        return conn
    return _create_connection()


def close_db_connection(exception=None):
    if not has_request_context():
        return
    conn = g.pop("_db_conn", None)
    if conn is None:
        return
    try:
        conn.close()
    except Exception:
        pass


def fetch_all(query, params=()):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(query, params)
        return cur.fetchall()
    finally:
        cur.close()
        if not has_request_context():
            conn.close()


def fetch_one(query, params=()):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(query, params)
        return cur.fetchone()
    finally:
        cur.close()
        if not has_request_context():
            conn.close()


def execute_query(query, params=()):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(query, params)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        if not has_request_context():
            conn.close()


def execute_query_returning(query, params=()):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(query, params)
        row = cur.fetchone()
        conn.commit()
        return row
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        if not has_request_context():
            conn.close()


def normalize_plate(plate: str) -> str:
    if not plate:
        return ""
    return "".join(plate.upper().split())


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS companies (
            id SERIAL PRIMARY KEY,
            name VARCHAR(150) UNIQUE NOT NULL,
            is_internal BOOLEAN DEFAULT FALSE,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS fuel_points (
            id SERIAL PRIMARY KEY,
            name VARCHAR(150) NOT NULL,
            point_type VARCHAR(30) NOT NULL,
            company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
            address TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS vehicles (
            id SERIAL PRIMARY KEY,
            company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
            division_name VARCHAR(100),
            brand VARCHAR(100) NOT NULL,
            vehicle_type VARCHAR(100),
            plate_number VARCHAR(50) NOT NULL,
            plate_normalized VARCHAR(50) UNIQUE NOT NULL,
            fuel_rate_km NUMERIC(12,2) DEFAULT 0,
            fuel_rate_mh NUMERIC(12,2) DEFAULT 0,
            fuel_rate_ground NUMERIC(12,2) DEFAULT 0,
            fuel_rate_climate NUMERIC(12,2) DEFAULT 0,
            fuel_rate_special NUMERIC(12,2) DEFAULT 0,
            fuel_rate_stops NUMERIC(12,2) DEFAULT 0,
            fuel_rate_load_30 NUMERIC(12,2) DEFAULT 0,
            fuel_rate_load_60 NUMERIC(12,2) DEFAULT 0,
            fuel_rate_load_75 NUMERIC(12,2) DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            full_name VARCHAR(150) NOT NULL,
            phone VARCHAR(30),
            username VARCHAR(80) UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role VARCHAR(30) NOT NULL,
            position VARCHAR(100),
            company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
            fuel_point_id INTEGER REFERENCES fuel_points(id) ON DELETE SET NULL,
            can_request_create BOOLEAN DEFAULT FALSE,
            can_request_approve BOOLEAN DEFAULT FALSE,
            can_request_check BOOLEAN DEFAULT FALSE,
            is_super_admin BOOLEAN DEFAULT FALSE,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS login_audit (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            username VARCHAR(80),
            full_name VARCHAR(150),
            role VARCHAR(30),
            company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
            company_name VARCHAR(150),
            login_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            logout_time TIMESTAMP NULL,
            ip_address VARCHAR(64),
            user_agent TEXT,
            browser_name VARCHAR(80),
            os_name VARCHAR(80),
            device_type VARCHAR(30),
            is_success BOOLEAN NOT NULL DEFAULT TRUE,
            fail_reason TEXT
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS fuel_opening_balances (
            id SERIAL PRIMARY KEY,
            fuel_point_id INTEGER NOT NULL REFERENCES fuel_points(id) ON DELETE CASCADE,
            balance_date DATE NOT NULL,
            liters NUMERIC(12,2) NOT NULL CHECK (liters >= 0),
            kg NUMERIC(12,2),
            density NUMERIC(10,4),
            temperature NUMERIC(10,2),
            comment TEXT,
            created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (fuel_point_id, balance_date)
        );
        """
    )



    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS fuel_requests (
            id SERIAL PRIMARY KEY,
            request_type VARCHAR(50) NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'draft',
            request_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            needed_at TIMESTAMP NULL,
            source_company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
            receiver_company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
            liability_company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
            source_fuel_point_id INTEGER REFERENCES fuel_points(id) ON DELETE SET NULL,
            source_point_name_manual VARCHAR(200),
            vehicle_id INTEGER REFERENCES vehicles(id) ON DELETE SET NULL,
            external_plate_number VARCHAR(50),
            driver_name VARCHAR(120),
            requested_liters NUMERIC(14,2) DEFAULT 0,
            requested_kg NUMERIC(14,2) DEFAULT 0,
            approved_liters NUMERIC(14,2) DEFAULT 0,
            approved_kg NUMERIC(14,2) DEFAULT 0,
            actual_liters NUMERIC(14,2) DEFAULT 0,
            actual_kg NUMERIC(14,2) DEFAULT 0,
            density NUMERIC(10,4),
            temperature NUMERIC(10,2),
            purpose TEXT,
            document_basis TEXT,
            document_number VARCHAR(120),
            approval_note TEXT,
            comment TEXT,
            requested_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            approved_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            checked_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            approved_at TIMESTAMP NULL,
            checked_at TIMESTAMP NULL,
            rejected_at TIMESTAMP NULL,
            fuel_transaction_id INTEGER REFERENCES fuel_transactions(id) ON DELETE SET NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS fuel_request_actions (
            id SERIAL PRIMARY KEY,
            request_id INTEGER NOT NULL REFERENCES fuel_requests(id) ON DELETE CASCADE,
            action_type VARCHAR(40) NOT NULL,
            old_status VARCHAR(30),
            new_status VARCHAR(30),
            action_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            note TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS fuel_transactions (
            id SERIAL PRIMARY KEY,
            operation_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            fuel_point_id INTEGER NOT NULL REFERENCES fuel_points(id) ON DELETE CASCADE,
            operation_type VARCHAR(30) NOT NULL,
            receiver_type VARCHAR(20) DEFAULT 'vehicle',
            liters NUMERIC(12,2) NOT NULL CHECK (liters >= 0),
            kg NUMERIC(12,2),
            density NUMERIC(10,4),
            temperature NUMERIC(10,2),
            vehicle_id INTEGER REFERENCES vehicles(id) ON DELETE SET NULL,
            destination_name VARCHAR(150),
            destination_point_id INTEGER REFERENCES fuel_points(id) ON DELETE SET NULL,
            document_date DATE,
            speedometer INTEGER,
            moto_hours NUMERIC(12,2),
            waybill_number VARCHAR(100),
            driver_name VARCHAR(150),
            source_kind VARCHAR(30),
            source_info TEXT,
            delivery_method VARCHAR(30),
            transport_reference VARCHAR(100),
            destination_info TEXT,
            task_basis TEXT,
            work_purpose TEXT,
            responsible_company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
            document_number VARCHAR(100),
            comment TEXT,
            entered_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            ats_checked_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            ats_checked_at TIMESTAMP,
            ats_comment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS company_reconciliation_openings (
            id SERIAL PRIMARY KEY,
            lender_company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            borrower_company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            balance_date DATE NOT NULL,
            liters NUMERIC(14,2) NOT NULL DEFAULT 0,
            kg NUMERIC(14,2) NOT NULL DEFAULT 0,
            comment TEXT,
            created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (lender_company_id, borrower_company_id, balance_date)
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS company_reconciliation_acts (
            id SERIAL PRIMARY KEY,
            lender_company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            borrower_company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            period_month DATE NOT NULL,
            act_number VARCHAR(120),
            act_date DATE,
            opening_liters NUMERIC(14,2) NOT NULL DEFAULT 0,
            opening_kg NUMERIC(14,2) NOT NULL DEFAULT 0,
            issued_liters NUMERIC(14,2) NOT NULL DEFAULT 0,
            issued_kg NUMERIC(14,2) NOT NULL DEFAULT 0,
            returned_liters NUMERIC(14,2) NOT NULL DEFAULT 0,
            returned_kg NUMERIC(14,2) NOT NULL DEFAULT 0,
            closing_liters NUMERIC(14,2) NOT NULL DEFAULT 0,
            closing_kg NUMERIC(14,2) NOT NULL DEFAULT 0,
            note TEXT,
            created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (lender_company_id, borrower_company_id, period_month)
        );
        """
    )

    # migrations for old databases
    cur.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS is_internal BOOLEAN DEFAULT FALSE;")

    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS position VARCHAR(100);")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS can_request_create BOOLEAN DEFAULT FALSE;")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS can_request_approve BOOLEAN DEFAULT FALSE;")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS can_request_check BOOLEAN DEFAULT FALSE;")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_super_admin BOOLEAN DEFAULT FALSE;")

    cur.execute("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS division_name VARCHAR(100);")
    cur.execute("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS fuel_rate_km NUMERIC(12,2) DEFAULT 0;")
    cur.execute("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS fuel_rate_mh NUMERIC(12,2) DEFAULT 0;")
    cur.execute("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS fuel_rate_ground NUMERIC(12,2) DEFAULT 0;")
    cur.execute("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS fuel_rate_climate NUMERIC(12,2) DEFAULT 0;")
    cur.execute("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS fuel_rate_special NUMERIC(12,2) DEFAULT 0;")
    cur.execute("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS fuel_rate_stops NUMERIC(12,2) DEFAULT 0;")
    cur.execute("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS fuel_rate_load_30 NUMERIC(12,2) DEFAULT 0;")
    cur.execute("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS fuel_rate_load_60 NUMERIC(12,2) DEFAULT 0;")
    cur.execute("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS fuel_rate_load_75 NUMERIC(12,2) DEFAULT 0;")

    cur.execute("ALTER TABLE fuel_opening_balances ADD COLUMN IF NOT EXISTS kg NUMERIC(12,2);")
    cur.execute("ALTER TABLE fuel_opening_balances ADD COLUMN IF NOT EXISTS density NUMERIC(10,4);")
    cur.execute("ALTER TABLE fuel_opening_balances ADD COLUMN IF NOT EXISTS temperature NUMERIC(10,2);")

    cur.execute("ALTER TABLE fuel_requests ADD COLUMN IF NOT EXISTS liability_company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL;")
    cur.execute("ALTER TABLE fuel_requests ADD COLUMN IF NOT EXISTS approval_note TEXT;")

    cur.execute("ALTER TABLE fuel_transactions ADD COLUMN IF NOT EXISTS receiver_type VARCHAR(20) DEFAULT 'vehicle';")
    cur.execute("ALTER TABLE fuel_transactions ADD COLUMN IF NOT EXISTS kg NUMERIC(12,2);")
    cur.execute("ALTER TABLE fuel_transactions ADD COLUMN IF NOT EXISTS density NUMERIC(10,4);")
    cur.execute("ALTER TABLE fuel_transactions ADD COLUMN IF NOT EXISTS temperature NUMERIC(10,2);")
    cur.execute("ALTER TABLE fuel_transactions ADD COLUMN IF NOT EXISTS destination_name VARCHAR(150);")
    cur.execute("ALTER TABLE fuel_transactions ADD COLUMN IF NOT EXISTS destination_point_id INTEGER REFERENCES fuel_points(id) ON DELETE SET NULL;")
    cur.execute("ALTER TABLE fuel_transactions ADD COLUMN IF NOT EXISTS document_date DATE;")
    cur.execute("ALTER TABLE fuel_transactions ADD COLUMN IF NOT EXISTS source_kind VARCHAR(30);")
    cur.execute("ALTER TABLE fuel_transactions ADD COLUMN IF NOT EXISTS delivery_method VARCHAR(30);")
    cur.execute("ALTER TABLE fuel_transactions ADD COLUMN IF NOT EXISTS transport_reference VARCHAR(100);")
    cur.execute("ALTER TABLE fuel_transactions ADD COLUMN IF NOT EXISTS moto_hours NUMERIC(12,2);")
    cur.execute("ALTER TABLE fuel_transactions ADD COLUMN IF NOT EXISTS waybill_number VARCHAR(100);")
    cur.execute("ALTER TABLE fuel_transactions ADD COLUMN IF NOT EXISTS driver_name VARCHAR(150);")

    # performance indexes
    cur.execute("CREATE INDEX IF NOT EXISTS idx_companies_active ON companies (is_active, name);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fuel_points_company_active ON fuel_points (company_id, is_active, point_type, name);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_vehicles_company_active ON vehicles (company_id, is_active, id DESC);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_vehicles_plate_normalized ON vehicles (plate_normalized);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_users_username_active ON users (username, is_active);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_users_company_active ON users (company_id, is_active);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_opening_balances_point_date ON fuel_opening_balances (fuel_point_id, balance_date DESC);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fuel_requests_status_date ON fuel_requests (status, request_date DESC, id DESC);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fuel_requests_source_company_status ON fuel_requests (source_company_id, status, request_date DESC, id DESC);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fuel_requests_receiver_company_date ON fuel_requests (receiver_company_id, request_date DESC, id DESC);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fuel_requests_liability_company_date ON fuel_requests (liability_company_id, request_date DESC, id DESC);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fuel_requests_requested_by_date ON fuel_requests (requested_by, request_date DESC, id DESC);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fuel_requests_point_status ON fuel_requests (source_fuel_point_id, status, request_date DESC, id DESC);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_recon_openings_pair_date ON company_reconciliation_openings (lender_company_id, borrower_company_id, balance_date DESC);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_recon_acts_pair_month ON company_reconciliation_acts (lender_company_id, borrower_company_id, period_month DESC);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fuel_transactions_point_date ON fuel_transactions (fuel_point_id, operation_date DESC, id DESC);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fuel_transactions_status_date ON fuel_transactions (status, operation_date DESC, id DESC);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fuel_transactions_vehicle_date ON fuel_transactions (vehicle_id, operation_date DESC, id DESC);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fuel_transactions_destination_point_date ON fuel_transactions (destination_point_id, operation_date DESC, id DESC);")

    conn.commit()

    cur.execute("SELECT id FROM companies WHERE name = %s", ("Eriell",))
    if not cur.fetchone():
        cur.execute("INSERT INTO companies (name, is_internal) VALUES (%s, TRUE)", ("Eriell",))
        conn.commit()
    else:
        cur.execute("UPDATE companies SET is_internal = TRUE WHERE name = %s", ("Eriell",))
        conn.commit()

    cur.execute("SELECT id FROM users WHERE username = %s", ("admin",))
    admin_row = cur.fetchone()
    if not admin_row:
        cur.execute(
            """
            INSERT INTO users (full_name, phone, username, password_hash, role, position, is_super_admin)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                "Главный администратор",
                "",
                "admin",
                generate_password_hash("admin123"),
                "admin",
                "Администратор",
                True,
            ),
        )
        conn.commit()
    else:
        cur.execute("UPDATE users SET is_super_admin = TRUE WHERE username = %s", ("admin",))
        conn.commit()

    cur.close()
    conn.close()
