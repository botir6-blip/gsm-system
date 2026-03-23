import os
import psycopg
from psycopg.rows import dict_row

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
        full_name VARCHAR(150),
        username VARCHAR(100),
        password_hash TEXT,
        role VARCHAR(30),
        company_id INTEGER,
        is_active BOOLEAN DEFAULT TRUE
    )
    """)

    # минимал версия (кейин кенгайтирамиз)

    conn.commit()
    cur.close()
    conn.close()
