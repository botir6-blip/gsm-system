import os
from functools import wraps

import psycopg
from psycopg.rows import dict_row
from flask import (
    Flask, request, redirect, url_for, render_template_string,
    flash, session
)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "supersecretkey")

DATABASE_URL = os.environ.get("DATABASE_URL")


# =========================
# DB
# =========================
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

    # companies
    cur.execute("""
    CREATE TABLE IF NOT EXISTS companies (
        id SERIAL PRIMARY KEY,
        name VARCHAR(150) NOT NULL UNIQUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # USERS (фақат битта!)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        full_name VARCHAR(150) NOT NULL,
        username VARCHAR(100) NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        role VARCHAR(30) NOT NULL,
        company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()

    # ADMIN
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
    
    # objects
    cur.execute("""
    CREATE TABLE IF NOT EXISTS objects (
        id SERIAL PRIMARY KEY,
        name VARCHAR(150) NOT NULL,
        company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # vehicles
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

    # fuel_requests
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

    # journal
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

    # migrations
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
        "is_active": "BOOLEAN NOT NULL DEFAULT TRUE"
    }
    for col_name, col_type in user_columns.items():
        if not column_exists(cur, "users", col_name):
            cur.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")

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

    # default admin
    admin = fetch_one("SELECT * FROM users WHERE username=%s", ("admin",))
    if not admin:
        cur.execute("""
            INSERT INTO users (full_name, username, password_hash, role, is_active)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            "Administrator",
            "admin",
            generate_password_hash("admin123"),
            "admin",
            True
        ))

    conn.commit()
    cur.close()
    conn.close()


try:
    init_db()
    print("✅ DB тайёр")
except Exception as e:
    print("❌ DB хатолик:", e)


# =========================
# AUTH / ROLES
# =========================
def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return fetch_one("""
        SELECT u.*, c.name AS company_name
        FROM users u
        LEFT JOIN companies c ON u.company_id = c.id
        WHERE u.id = %s AND u.is_active = TRUE
    """, (user_id,))


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user():
            flash("Сначала войдите в систему.", "error")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


def role_required(*roles):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user:
                flash("Сначала войдите в систему.", "error")
                return redirect(url_for("login"))
            if user["role"] not in roles:
                flash("У вас нет доступа к этому разделу.", "error")
                return redirect(url_for("index"))
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def nav_menu():
    user = current_user()
    if not user:
        return f"""
        <div class="menu">
            <a href="{url_for('login')}">Вход</a>
        </div>
        """

    menu = [f'<a href="{url_for("index")}">Главная</a>']

    if user["role"] == "admin":
        menu += [
            f'<a href="{url_for("companies_page")}">Компании</a>',
            f'<a href="{url_for("objects_page")}">Объекты</a>',
            f'<a href="{url_for("vehicles_page")}">Транспорт</a>',
            f'<a href="{url_for("users_page")}">Пользователи</a>',
        ]

    if user["role"] in ["admin", "requester"]:
        menu.append(f'<a href="{url_for("new_request_page")}">Новая заявка</a>')

    menu.append(f'<a href="{url_for("requests_page")}">Заявки</a>')
    menu.append(f'<a href="{url_for("transactions_page")}">Журнал</a>')
    menu.append(f'<a href="{url_for("logout")}">Выход</a>')

    return f'<div class="menu">{"".join(menu)}</div>'


# =========================
# HTML
# =========================
BASE_HTML = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>{{ title }}</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background: linear-gradient(135deg, #eef4ff 0%, #f7fbff 100%);
            margin: 0;
            padding: 20px;
            color: #1f2937;
        }
        .container {
            max-width: 1360px;
            margin: auto;
            background: #ffffff;
            padding: 22px;
            border-radius: 18px;
            box-shadow: 0 10px 30px rgba(31,41,55,0.08);
        }
        .topbar {
            display: flex;
            justify-content: space-between;
            gap: 12px;
            align-items: center;
            margin-bottom: 18px;
            flex-wrap: wrap;
        }
        .userbox {
            background: #f3f6fb;
            border: 1px solid #dbe4f0;
            padding: 10px 14px;
            border-radius: 12px;
            font-size: 14px;
        }
        h1, h2, h3 {
            margin-top: 0;
        }
        .menu {
            margin-bottom: 20px;
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
        }
        .menu a {
            text-decoration: none;
            background: #2563eb;
            color: white;
            padding: 10px 14px;
            border-radius: 10px;
            display: inline-block;
            font-size: 14px;
            box-shadow: 0 4px 12px rgba(37,99,235,0.18);
        }
        .menu a:hover {
            background: #1d4ed8;
        }
        .dashboard {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 16px;
            margin-bottom: 18px;
        }
        .stat {
            background: linear-gradient(135deg, #ffffff 0%, #f7faff 100%);
            border: 1px solid #dbe4f0;
            border-radius: 16px;
            padding: 18px;
            box-shadow: 0 6px 18px rgba(31,41,55,0.06);
        }
        .stat .label {
            font-size: 13px;
            color: #6b7280;
            margin-bottom: 8px;
        }
        .stat .value {
            font-size: 28px;
            font-weight: bold;
        }
        .grid-2 {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 18px;
        }
        .card {
            background: #f9fbff;
            border: 1px solid #e3ebf5;
            padding: 18px;
            border-radius: 16px;
            margin-bottom: 18px;
            box-shadow: 0 6px 16px rgba(31,41,55,0.05);
        }
        form {
            display: grid;
            gap: 12px;
        }
        input, select, textarea, button {
            padding: 12px;
            border-radius: 12px;
            border: 1px solid #cfd8e3;
            font-size: 15px;
            box-sizing: border-box;
            width: 100%;
            background: #fff;
        }
        textarea {
            min-height: 90px;
            resize: vertical;
        }
        button {
            background: linear-gradient(135deg, #16a34a 0%, #179c54 100%);
            color: white;
            border: none;
            cursor: pointer;
            font-weight: bold;
            box-shadow: 0 6px 16px rgba(22,163,74,0.2);
        }
        button:hover {
            background: #15803d;
        }
        .btn-red {
            background: linear-gradient(135deg, #dc2626 0%, #c81e1e 100%) !important;
        }
        .btn-red:hover {
            background: #b91c1c !important;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
            background: white;
            font-size: 14px;
            border-radius: 14px;
            overflow: hidden;
        }
        th, td {
            border: 1px solid #e5e7eb;
            padding: 10px;
            text-align: left;
            vertical-align: top;
        }
        th {
            background: #eef4fb;
        }
        .flash {
            padding: 12px;
            border-radius: 12px;
            margin-bottom: 15px;
        }
        .success {
            background: #dcfce7;
            color: #166534;
        }
        .error {
            background: #fee2e2;
            color: #991b1b;
        }
        .actions {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
        }
        .btn {
            padding: 7px 10px;
            color: white;
            border-radius: 9px;
            text-decoration: none;
            font-size: 13px;
            display: inline-block;
        }
        .btn-edit { background: #f59e0b; }
        .btn-edit:hover { background: #d97706; }

        .btn-delete { background: #dc2626; }
        .btn-delete:hover { background: #b91c1c; }

        .btn-view { background: #2563eb; }
        .btn-view:hover { background: #1d4ed8; }

        .btn-approve { background: #0ea5e9; }
        .btn-approve:hover { background: #0284c7; }

        .btn-fuel { background: #16a34a; }
        .btn-fuel:hover { background: #15803d; }

        .btn-check { background: #7c3aed; }
        .btn-check:hover { background: #6d28d9; }

        .btn-back { background: #6b7280; }
        .btn-back:hover { background: #4b5563; }

        .status {
            display: inline-block;
            padding: 5px 10px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: bold;
            color: #fff;
        }
        .status-new { background: #6b7280; }
        .status-approved { background: #0ea5e9; }
        .status-fueled { background: #16a34a; }
        .status-checked { background: #7c3aed; }
        .status-rejected { background: #dc2626; }

        @media (max-width: 1100px) {
            .dashboard {
                grid-template-columns: repeat(2, 1fr);
            }
            .grid-2 {
                grid-template-columns: 1fr;
            }
        }
        @media (max-width: 700px) {
            .dashboard {
                grid-template-columns: 1fr;
            }
            .container {
                padding: 14px;
            }
            table {
                font-size: 13px;
            }
        }
    </style>
</head>
<body>
<div class="container">
    <div class="topbar">
        <h1>{{ title }}</h1>
        {{ user_box|safe }}
    </div>

    {{ menu|safe }}

    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        {% for category, message in messages %}
          <div class="flash {{ category }}">{{ message }}</div>
        {% endfor %}
      {% endif %}
    {% endwith %}

    {{ content|safe }}
</div>
</body>
</html>
"""


def render_page(title, content):
    user = current_user()
    if user:
        user_box = f"""
        <div class="userbox">
            <b>{user['full_name']}</b><br>
            Логин: {user['username']} |
            Роль: {user['role']} |
            Компания: {user['company_name'] or '-'}
        </div>
        """
    else:
        user_box = '<div class="userbox">Гость</div>'

    return render_template_string(
        BASE_HTML,
        title=title,
        content=content,
        menu=nav_menu(),
        user_box=user_box
    )


def status_badge(status):
    labels = {
        "new": ("Новая", "status-new"),
        "approved": ("Разрешена", "status-approved"),
        "fueled": ("Заправлена", "status-fueled"),
        "checked": ("Проверена", "status-checked"),
        "rejected": ("Отклонена", "status-rejected"),
    }
    text, css = labels.get(status, (status, "status-new"))
    return f'<span class="status {css}">{text}</span>'


# =========================
# LOGIN / LOGOUT
# =========================
@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        user = fetch_one("""
            SELECT *
            FROM users
            WHERE username = %s AND is_active = TRUE
        """, (username,))

        if not user or not check_password_hash(user["password_hash"], password):
            flash("Неверный логин или пароль.", "error")
            return redirect(url_for("login"))

        session["user_id"] = user["id"]
        flash("Вход выполнен.", "success")
        return redirect(url_for("index"))

    content = """
    <div class="card" style="max-width:520px; margin:auto;">
        <h3>Вход в систему</h3>
        <form method="POST">
            <input type="text" name="username" placeholder="Логин" required>
            <input type="password" name="password" placeholder="Пароль" required>
            <button type="submit">Войти</button>
        </form>
        <p><b>Стартовый админ:</b> admin / admin123</p>
    </div>
    """
    return render_page("Вход", content)


@app.route("/logout")
def logout():
    session.clear()
    flash("Вы вышли из системы.", "success")
    return redirect(url_for("login"))


# =========================
# DASHBOARD
# =========================
@app.route("/")
@login_required
def index():
    user = current_user()

    if user["role"] == "admin":
        company_count = fetch_one("SELECT COUNT(*) AS cnt FROM companies")["cnt"]
        object_count = fetch_one("SELECT COUNT(*) AS cnt FROM objects")["cnt"]
        vehicle_count = fetch_one("SELECT COUNT(*) AS cnt FROM vehicles")["cnt"]
        request_total = fetch_one("SELECT COUNT(*) AS cnt FROM fuel_requests")["cnt"]
        new_count = fetch_one("SELECT COUNT(*) AS cnt FROM fuel_requests WHERE status='new'")["cnt"]
        approved_count = fetch_one("SELECT COUNT(*) AS cnt FROM fuel_requests WHERE status='approved'")["cnt"]
        fueled_count = fetch_one("SELECT COUNT(*) AS cnt FROM fuel_requests WHERE status='fueled'")["cnt"]
        checked_count = fetch_one("SELECT COUNT(*) AS cnt FROM fuel_requests WHERE status='checked'")["cnt"]
    else:
        company_id = user["company_id"]
        company_count = 1 if company_id else 0
        object_count = fetch_one("SELECT COUNT(*) AS cnt FROM objects WHERE company_id=%s", (company_id,))["cnt"] if company_id else 0
        vehicle_count = fetch_one("SELECT COUNT(*) AS cnt FROM vehicles WHERE company_id=%s", (company_id,))["cnt"] if company_id else 0
        request_total = fetch_one("SELECT COUNT(*) AS cnt FROM fuel_requests WHERE requester_company_id=%s", (company_id,))["cnt"] if company_id else 0
        new_count = fetch_one("SELECT COUNT(*) AS cnt FROM fuel_requests WHERE requester_company_id=%s AND status='new'", (company_id,))["cnt"] if company_id else 0
        approved_count = fetch_one("SELECT COUNT(*) AS cnt FROM fuel_requests WHERE requester_company_id=%s AND status='approved'", (company_id,))["cnt"] if company_id else 0
        fueled_count = fetch_one("SELECT COUNT(*) AS cnt FROM fuel_requests WHERE requester_company_id=%s AND status='fueled'", (company_id,))["cnt"] if company_id else 0
        checked_count = fetch_one("SELECT COUNT(*) AS cnt FROM fuel_requests WHERE requester_company_id=%s AND status='checked'", (company_id,))["cnt"] if company_id else 0

    content = f"""
    <div class="dashboard">
        <div class="stat">
            <div class="label">Компании</div>
            <div class="value">{company_count}</div>
        </div>
        <div class="stat">
            <div class="label">Объекты</div>
            <div class="value">{object_count}</div>
        </div>
        <div class="stat">
            <div class="label">Транспорт</div>
            <div class="value">{vehicle_count}</div>
        </div>
        <div class="stat">
            <div class="label">Всего заявок</div>
            <div class="value">{request_total}</div>
        </div>
        <div class="stat">
            <div class="label">Новые</div>
            <div class="value">{new_count}</div>
        </div>
        <div class="stat">
            <div class="label">Разрешенные</div>
            <div class="value">{approved_count}</div>
        </div>
        <div class="stat">
            <div class="label">Заправленные</div>
            <div class="value">{fueled_count}</div>
        </div>
        <div class="stat">
            <div class="label">Проверенные</div>
            <div class="value">{checked_count}</div>
        </div>
    </div>

    <div class="grid-2">
        <div class="card">
            <h3>Ваш доступ</h3>
            <p><b>Роль:</b> {user['role']}</p>
            <p><b>Пользователь:</b> {user['full_name']}</p>
            <p><b>Компания:</b> {user['company_name'] or '-'}</p>
        </div>
        <div class="card">
            <h3>Порядок работы</h3>
            <p>1. requester — создает заявку</p>
            <p>2. approver — рассматривает и указывает поставщика дизеля</p>
            <p>3. fueler — вводит фактическую заправку</p>
            <p>4. controller — завершает проверку</p>
            <p>admin — управляет справочниками и пользователями</p>
        </div>
    </div>
    """
    return render_page("Dashboard системы ГСМ", content)


# =========================
# USERS
# =========================
@app.route("/users", methods=["GET", "POST"])
@login_required
@role_required("admin")
def users_page():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        role = request.form.get("role", "").strip()
        company_id = request.form.get("company_id") or None

        if not full_name or not username or not password or not role:
            flash("Заполните обязательные поля.", "error")
            return redirect(url_for("users_page"))

        existing = fetch_one("SELECT * FROM users WHERE username=%s", (username,))
        if existing:
            flash("Такой логин уже существует.", "error")
            return redirect(url_for("users_page"))

        execute_query("""
            INSERT INTO users (full_name, username, password_hash, role, company_id, is_active)
            VALUES (%s, %s, %s, %s, %s, TRUE)
        """, (
            full_name,
            username,
            generate_password_hash(password),
            role,
            company_id
        ))

        flash("Пользователь создан.", "success")
        return redirect(url_for("users_page"))

    companies = fetch_all("SELECT * FROM companies ORDER BY name")
    users = fetch_all("""
        SELECT u.*, c.name AS company_name
        FROM users u
        LEFT JOIN companies c ON u.company_id = c.id
        ORDER BY u.id DESC
    """)

    company_options = "".join(
        [f"<option value='{c['id']}'>{c['name']}</option>" for c in companies]
    )

    rows = ""
    for u in users:
        rows += f"""
        <tr>
            <td>{u['id']}</td>
            <td>{u['full_name']}</td>
            <td>{u['username']}</td>
            <td>{u['role']}</td>
            <td>{u['company_name'] or ''}</td>
            <td>{"Да" if u['is_active'] else "Нет"}</td>
            <td>
                <div class="actions">
                    <a class="btn btn-edit" href="/users/edit/{u['id']}">Редактировать</a>
                </div>
            </td>
        </tr>
        """

    content = f"""
    <div class="card">
        <h3>Добавить пользователя</h3>
        <form method="POST">
            <input type="text" name="full_name" placeholder="ФИО" required>
            <input type="text" name="username" placeholder="Логин" required>
            <input type="password" name="password" placeholder="Пароль" required>
            <select name="role" required>
                <option value="">Выберите роль</option>
                <option value="admin">admin</option>
                <option value="requester">requester</option>
                <option value="approver">approver</option>
                <option value="fueler">fueler</option>
                <option value="controller">controller</option>
            </select>
            <select name="company_id">
                <option value="">Компания (необязательно для admin)</option>
                {company_options}
            </select>
            <button type="submit">Сохранить</button>
        </form>
    </div>

    <div class="card">
        <h3>Пользователи</h3>
        <table>
            <tr>
                <th>ID</th>
                <th>ФИО</th>
                <th>Логин</th>
                <th>Роль</th>
                <th>Компания</th>
                <th>Активен</th>
                <th>Действия</th>
            </tr>
            {rows}
        </table>
    </div>
    """
    return render_page("Пользователи", content)


@app.route("/users/edit/<int:user_id>", methods=["GET", "POST"])
@login_required
@role_required("admin")
def edit_user(user_id):
    user_row = fetch_one("SELECT * FROM users WHERE id=%s", (user_id,))
    if not user_row:
        flash("Пользователь не найден.", "error")
        return redirect(url_for("users_page"))

    companies = fetch_all("SELECT * FROM companies ORDER BY name")

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        role = request.form.get("role", "").strip()
        company_id = request.form.get("company_id") or None
        is_active = True if request.form.get("is_active") == "on" else False

        if not full_name or not username or not role:
            flash("Заполните обязательные поля.", "error")
            return redirect(url_for("edit_user", user_id=user_id))

        existing = fetch_one("SELECT * FROM users WHERE username=%s AND id<>%s", (username, user_id))
        if existing:
            flash("Другой пользователь с таким логином уже существует.", "error")
            return redirect(url_for("edit_user", user_id=user_id))

        if password:
            execute_query("""
                UPDATE users
                SET full_name=%s, username=%s, password_hash=%s, role=%s, company_id=%s, is_active=%s
                WHERE id=%s
            """, (
                full_name, username, generate_password_hash(password), role, company_id, is_active, user_id
            ))
        else:
            execute_query("""
                UPDATE users
                SET full_name=%s, username=%s, role=%s, company_id=%s, is_active=%s
                WHERE id=%s
            """, (
                full_name, username, role, company_id, is_active, user_id
            ))

        flash("Пользователь обновлен.", "success")
        return redirect(url_for("users_page"))

    company_options = "".join([
        f"<option value='{c['id']}' {'selected' if c['id'] == user_row['company_id'] else ''}>{c['name']}</option>"
        for c in companies
    ])

    checked = "checked" if user_row["is_active"] else ""

    content = f"""
    <div class="card">
        <h3>Редактирование пользователя</h3>
        <form method="POST">
            <input type="text" name="full_name" value="{user_row['full_name']}" required>
            <input type="text" name="username" value="{user_row['username']}" required>
            <input type="password" name="password" placeholder="Новый пароль (если нужно)">
            <select name="role" required>
                <option value="admin" {"selected" if user_row["role"]=="admin" else ""}>admin</option>
                <option value="requester" {"selected" if user_row["role"]=="requester" else ""}>requester</option>
                <option value="approver" {"selected" if user_row["role"]=="approver" else ""}>approver</option>
                <option value="fueler" {"selected" if user_row["role"]=="fueler" else ""}>fueler</option>
                <option value="controller" {"selected" if user_row["role"]=="controller" else ""}>controller</option>
            </select>
            <select name="company_id">
                <option value="">Компания</option>
                {company_options}
            </select>
            <label><input type="checkbox" name="is_active" {checked}> Активен</label>
            <button type="submit">Сохранить изменения</button>
        </form>
        <br>
        <a class="btn btn-back" href="{url_for('users_page')}">Назад</a>
    </div>
    """
    return render_page("Редактирование пользователя", content)


# =========================
# COMPANIES
# =========================
@app.route("/companies", methods=["GET", "POST"])
@login_required
@role_required("admin")
def companies_page():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Введите название компании.", "error")
            return redirect(url_for("companies_page"))

        existing = fetch_one("SELECT * FROM companies WHERE LOWER(name)=LOWER(%s)", (name,))
        if existing:
            flash("Такая компания уже существует.", "error")
            return redirect(url_for("companies_page"))

        execute_query("INSERT INTO companies (name) VALUES (%s)", (name,))
        flash("Компания добавлена.", "success")
        return redirect(url_for("companies_page"))

    companies = fetch_all("SELECT * FROM companies ORDER BY id DESC")

    rows = ""
    for c in companies:
        rows += f"""
        <tr>
            <td>{c['id']}</td>
            <td>{c['name']}</td>
            <td>
                <div class="actions">
                    <a class="btn btn-edit" href="/companies/edit/{c['id']}">Редактировать</a>
                    <a class="btn btn-delete" href="/companies/delete/{c['id']}" onclick="return confirm('Удалить компанию?')">Удалить</a>
                </div>
            </td>
        </tr>
        """

    content = f"""
    <div class="card">
        <h3>Добавить компанию</h3>
        <form method="POST">
            <input type="text" name="name" placeholder="Название компании" required>
            <button type="submit">Сохранить</button>
        </form>
    </div>
    <div class="card">
        <h3>Список компаний</h3>
        <table>
            <tr><th>ID</th><th>Название</th><th>Действия</th></tr>
            {rows}
        </table>
    </div>
    """
    return render_page("Компании", content)


@app.route("/companies/edit/<int:company_id>", methods=["GET", "POST"])
@login_required
@role_required("admin")
def edit_company(company_id):
    company = fetch_one("SELECT * FROM companies WHERE id=%s", (company_id,))
    if not company:
        flash("Компания не найдена.", "error")
        return redirect(url_for("companies_page"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Введите название компании.", "error")
            return redirect(url_for("edit_company", company_id=company_id))

        existing = fetch_one("SELECT * FROM companies WHERE LOWER(name)=LOWER(%s) AND id<>%s", (name, company_id))
        if existing:
            flash("Другая компания с таким названием уже существует.", "error")
            return redirect(url_for("edit_company", company_id=company_id))

        execute_query("UPDATE companies SET name=%s WHERE id=%s", (name, company_id))
        flash("Компания обновлена.", "success")
        return redirect(url_for("companies_page"))

    content = f"""
    <div class="card">
        <h3>Редактирование компании</h3>
        <form method="POST">
            <input type="text" name="name" value="{company['name']}" required>
            <button type="submit">Сохранить изменения</button>
        </form>
        <br>
        <a class="btn btn-back" href="{url_for('companies_page')}">Назад</a>
    </div>
    """
    return render_page("Редактирование компании", content)


@app.route("/companies/delete/<int:company_id>")
@login_required
@role_required("admin")
def delete_company(company_id):
    execute_query("DELETE FROM companies WHERE id=%s", (company_id,))
    flash("Компания удалена.", "success")
    return redirect(url_for("companies_page"))


# =========================
# OBJECTS
# =========================
@app.route("/objects", methods=["GET", "POST"])
@login_required
@role_required("admin")
def objects_page():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        company_id = request.form.get("company_id")

        if not name or not company_id:
            flash("Введите название объекта и выберите компанию.", "error")
            return redirect(url_for("objects_page"))

        existing = fetch_one("""
            SELECT * FROM objects
            WHERE LOWER(name)=LOWER(%s) AND company_id=%s
        """, (name, company_id))
        if existing:
            flash("Такой объект уже существует у этой компании.", "error")
            return redirect(url_for("objects_page"))

        execute_query("INSERT INTO objects (name, company_id) VALUES (%s, %s)", (name, company_id))
        flash("Объект добавлен.", "success")
        return redirect(url_for("objects_page"))

    companies = fetch_all("SELECT * FROM companies ORDER BY name")
    objects = fetch_all("""
        SELECT o.id, o.name, c.name AS company_name
        FROM objects o
        LEFT JOIN companies c ON o.company_id = c.id
        ORDER BY o.id DESC
    """)

    company_options = "".join([f"<option value='{c['id']}'>{c['name']}</option>" for c in companies])

    rows = ""
    for o in objects:
        rows += f"""
        <tr>
            <td>{o['id']}</td>
            <td>{o['name']}</td>
            <td>{o['company_name'] or ''}</td>
            <td>
                <div class="actions">
                    <a class="btn btn-edit" href="/objects/edit/{o['id']}">Редактировать</a>
                    <a class="btn btn-delete" href="/objects/delete/{o['id']}" onclick="return confirm('Удалить объект?')">Удалить</a>
                </div>
            </td>
        </tr>
        """

    content = f"""
    <div class="card">
        <h3>Добавить объект</h3>
        <form method="POST">
            <input type="text" name="name" placeholder="Название объекта" required>
            <select name="company_id" required>
                <option value="">Выберите компанию</option>
                {company_options}
            </select>
            <button type="submit">Сохранить</button>
        </form>
    </div>
    <div class="card">
        <h3>Список объектов</h3>
        <table>
            <tr><th>ID</th><th>Объект</th><th>Компания</th><th>Действия</th></tr>
            {rows}
        </table>
    </div>
    """
    return render_page("Объекты", content)


@app.route("/objects/edit/<int:object_id>", methods=["GET", "POST"])
@login_required
@role_required("admin")
def edit_object(object_id):
    obj = fetch_one("SELECT * FROM objects WHERE id=%s", (object_id,))
    if not obj:
        flash("Объект не найден.", "error")
        return redirect(url_for("objects_page"))

    companies = fetch_all("SELECT * FROM companies ORDER BY name")

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        company_id = request.form.get("company_id")

        if not name or not company_id:
            flash("Введите название объекта и выберите компанию.", "error")
            return redirect(url_for("edit_object", object_id=object_id))

        existing = fetch_one("""
            SELECT * FROM objects
            WHERE LOWER(name)=LOWER(%s) AND company_id=%s AND id<>%s
        """, (name, company_id, object_id))
        if existing:
            flash("Такой объект уже существует у этой компании.", "error")
            return redirect(url_for("edit_object", object_id=object_id))

        execute_query("UPDATE objects SET name=%s, company_id=%s WHERE id=%s", (name, company_id, object_id))
        flash("Объект обновлен.", "success")
        return redirect(url_for("objects_page"))

    company_options = "".join([
        f"<option value='{c['id']}' {'selected' if c['id'] == obj['company_id'] else ''}>{c['name']}</option>"
        for c in companies
    ])

    content = f"""
    <div class="card">
        <h3>Редактирование объекта</h3>
        <form method="POST">
            <input type="text" name="name" value="{obj['name']}" required>
            <select name="company_id" required>
                <option value="">Выберите компанию</option>
                {company_options}
            </select>
            <button type="submit">Сохранить изменения</button>
        </form>
        <br>
        <a class="btn btn-back" href="{url_for('objects_page')}">Назад</a>
    </div>
    """
    return render_page("Редактирование объекта", content)


@app.route("/objects/delete/<int:object_id>")
@login_required
@role_required("admin")
def delete_object(object_id):
    execute_query("DELETE FROM objects WHERE id=%s", (object_id,))
    flash("Объект удален.", "success")
    return redirect(url_for("objects_page"))


# =========================
# VEHICLES
# =========================
@app.route("/vehicles", methods=["GET", "POST"])
@login_required
@role_required("admin")
def vehicles_page():
    if request.method == "POST":
        brand = request.form.get("brand", "").strip()
        vehicle_type = request.form.get("vehicle_type", "").strip()
        plate_number = request.form.get("plate_number", "").strip()
        company_id = request.form.get("company_id")

        if not brand or not vehicle_type or not plate_number or not company_id:
            flash("Заполните все поля.", "error")
            return redirect(url_for("vehicles_page"))

        normalized = normalize_plate(plate_number)
        existing = fetch_one("SELECT * FROM vehicles WHERE plate_number_normalized=%s", (normalized,))
        if existing:
            flash("Такой транспорт уже существует. Дубликат госномера.", "error")
            return redirect(url_for("vehicles_page"))

        execute_query("""
            INSERT INTO vehicles (brand, vehicle_type, plate_number, plate_number_normalized, company_id)
            VALUES (%s, %s, %s, %s, %s)
        """, (brand, vehicle_type, plate_number, normalized, company_id))

        flash("Транспорт добавлен.", "success")
        return redirect(url_for("vehicles_page"))

    companies = fetch_all("SELECT * FROM companies ORDER BY name")
    vehicles = fetch_all("""
        SELECT v.id, v.brand, v.vehicle_type, v.plate_number, c.name AS company_name
        FROM vehicles v
        LEFT JOIN companies c ON v.company_id = c.id
        ORDER BY v.id DESC
    """)

    company_options = "".join([f"<option value='{c['id']}'>{c['name']}</option>" for c in companies])

    rows = ""
    for v in vehicles:
        rows += f"""
        <tr>
            <td>{v['id']}</td>
            <td>{v['brand']}</td>
            <td>{v['vehicle_type']}</td>
            <td>{v['plate_number']}</td>
            <td>{v['company_name'] or ''}</td>
            <td>
                <div class="actions">
                    <a class="btn btn-edit" href="/vehicles/edit/{v['id']}">Редактировать</a>
                    <a class="btn btn-delete" href="/vehicles/delete/{v['id']}" onclick="return confirm('Удалить транспорт?')">Удалить</a>
                </div>
            </td>
        </tr>
        """

    content = f"""
    <div class="card">
        <h3>Добавить транспорт</h3>
        <form method="POST">
            <input type="text" name="brand" placeholder="Марка автомобиля" required>
            <input type="text" name="vehicle_type" placeholder="Тип автомобиля" required>
            <input type="text" name="plate_number" placeholder="Гос. номер" required>
            <select name="company_id" required>
                <option value="">Выберите компанию</option>
                {company_options}
            </select>
            <button type="submit">Сохранить</button>
        </form>
    </div>
    <div class="card">
        <h3>Список транспорта</h3>
        <table>
            <tr><th>ID</th><th>Марка</th><th>Тип</th><th>Гос. номер</th><th>Компания</th><th>Действия</th></tr>
            {rows}
        </table>
    </div>
    """
    return render_page("Транспорт", content)


@app.route("/vehicles/edit/<int:vehicle_id>", methods=["GET", "POST"])
@login_required
@role_required("admin")
def edit_vehicle(vehicle_id):
    vehicle = fetch_one("SELECT * FROM vehicles WHERE id=%s", (vehicle_id,))
    if not vehicle:
        flash("Транспорт не найден.", "error")
        return redirect(url_for("vehicles_page"))

    companies = fetch_all("SELECT * FROM companies ORDER BY name")

    if request.method == "POST":
        brand = request.form.get("brand", "").strip()
        vehicle_type = request.form.get("vehicle_type", "").strip()
        plate_number = request.form.get("plate_number", "").strip()
        company_id = request.form.get("company_id")

        if not brand or not vehicle_type or not plate_number or not company_id:
            flash("Заполните все поля.", "error")
            return redirect(url_for("edit_vehicle", vehicle_id=vehicle_id))

        normalized = normalize_plate(plate_number)
        existing = fetch_one("""
            SELECT * FROM vehicles
            WHERE plate_number_normalized=%s AND id<>%s
        """, (normalized, vehicle_id))
        if existing:
            flash("Другой транспорт с таким госномером уже существует.", "error")
            return redirect(url_for("edit_vehicle", vehicle_id=vehicle_id))

        execute_query("""
            UPDATE vehicles
            SET brand=%s, vehicle_type=%s, plate_number=%s, plate_number_normalized=%s, company_id=%s
            WHERE id=%s
        """, (brand, vehicle_type, plate_number, normalized, company_id, vehicle_id))

        flash("Транспорт обновлен.", "success")
        return redirect(url_for("vehicles_page"))

    company_options = "".join([
        f"<option value='{c['id']}' {'selected' if c['id'] == vehicle['company_id'] else ''}>{c['name']}</option>"
        for c in companies
    ])

    content = f"""
    <div class="card">
        <h3>Редактирование транспорта</h3>
        <form method="POST">
            <input type="text" name="brand" value="{vehicle['brand']}" required>
            <input type="text" name="vehicle_type" value="{vehicle['vehicle_type']}" required>
            <input type="text" name="plate_number" value="{vehicle['plate_number']}" required>
            <select name="company_id" required>
                <option value="">Выберите компанию</option>
                {company_options}
            </select>
            <button type="submit">Сохранить изменения</button>
        </form>
        <br>
        <a class="btn btn-back" href="{url_for('vehicles_page')}">Назад</a>
    </div>
    """
    return render_page("Редактирование транспорта", content)


@app.route("/vehicles/delete/<int:vehicle_id>")
@login_required
@role_required("admin")
def delete_vehicle(vehicle_id):
    execute_query("DELETE FROM vehicles WHERE id=%s", (vehicle_id,))
    flash("Транспорт удален.", "success")
    return redirect(url_for("vehicles_page"))


# =========================
# NEW REQUEST
# =========================
@app.route("/requests/new", methods=["GET", "POST"])
@login_required
@role_required("admin", "requester")
def new_request_page():
    user = current_user()

    if request.method == "POST":
        requester_company_id = request.form.get("requester_company_id")
        object_id = request.form.get("object_id")
        vehicle_id = request.form.get("vehicle_id")
        requested_by = request.form.get("requested_by", "").strip()
        requester_position = request.form.get("requester_position", "").strip()
        project_name = request.form.get("project_name", "").strip()
        requested_liters = request.form.get("requested_liters", "").strip()
        request_comment = request.form.get("request_comment", "").strip()

        if user["role"] != "admin":
            requester_company_id = str(user["company_id"]) if user["company_id"] else None

        if not requester_company_id or not object_id or not vehicle_id or not requested_by or not requested_liters:
            flash("Заполните обязательные поля.", "error")
            return redirect(url_for("new_request_page"))

        obj = fetch_one("SELECT * FROM objects WHERE id=%s", (object_id,))
        veh = fetch_one("SELECT * FROM vehicles WHERE id=%s", (vehicle_id,))
        if not obj or not veh:
            flash("Неверно выбран объект или транспорт.", "error")
            return redirect(url_for("new_request_page"))

        if str(obj["company_id"]) != str(requester_company_id) or str(veh["company_id"]) != str(requester_company_id):
            flash("Объект и транспорт должны относиться к выбранной компании.", "error")
            return redirect(url_for("new_request_page"))

        try:
            liters_value = float(requested_liters)
            if liters_value <= 0:
                flash("Количество литров должно быть больше нуля.", "error")
                return redirect(url_for("new_request_page"))
        except ValueError:
            flash("Неверно указано количество литров.", "error")
            return redirect(url_for("new_request_page"))

        execute_query("""
            INSERT INTO fuel_requests (
                requester_company_id, object_id, vehicle_id,
                requested_by, requester_position, project_name,
                requested_liters, request_comment, status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'new')
        """, (
            requester_company_id, object_id, vehicle_id,
            requested_by, requester_position, project_name,
            liters_value, request_comment
        ))

        flash("Заявка создана.", "success")
        return redirect(url_for("requests_page"))

    if user["role"] == "admin":
        companies = fetch_all("SELECT * FROM companies ORDER BY name")
        selected_company_id = request.args.get("company_id") or ""
    else:
        companies = fetch_all("SELECT * FROM companies WHERE id=%s", (user["company_id"],)) if user["company_id"] else []
        selected_company_id = str(user["company_id"]) if user["company_id"] else ""

    if selected_company_id:
        objects = fetch_all("""
            SELECT o.id, o.name, c.name AS company_name
            FROM objects o
            LEFT JOIN companies c ON o.company_id = c.id
            WHERE o.company_id = %s
            ORDER BY o.name
        """, (selected_company_id,))

        vehicles = fetch_all("""
            SELECT v.id, v.brand, v.vehicle_type, v.plate_number, c.name AS company_name
            FROM vehicles v
            LEFT JOIN companies c ON v.company_id = c.id
            WHERE v.company_id = %s
            ORDER BY v.brand, v.plate_number
        """, (selected_company_id,))
    else:
        objects = []
        vehicles = []

    company_options = "".join([
        f"<option value='{c['id']}' {'selected' if str(c['id']) == str(selected_company_id) else ''}>{c['name']}</option>"
        for c in companies
    ])

    object_options = "".join([
        f"<option value='{o['id']}'>{o['name']} / {o['company_name'] or ''}</option>"
        for o in objects
    ])

    vehicle_options = "".join([
        f"<option value='{v['id']}'>{v['brand']} / {v['vehicle_type']} / {v['plate_number']}</option>"
        for v in vehicles
    ])

    company_selector = ""
    if user["role"] == "admin":
        company_selector = f"""
        <select name="requester_company_id" id="requester_company_id" required onchange="filterByCompany(this.value)">
            <option value="">Компания-заявитель</option>
            {company_options}
        </select>
        """
    else:
        company_selector = f"""
        <input type="hidden" name="requester_company_id" value="{selected_company_id}">
        <input type="text" value="{user['company_name'] or ''}" readonly>
        """

    content = f"""
    <div class="card">
        <h3>Новая заявка на ГСМ</h3>
        <form method="POST">
            {company_selector}
            <input type="text" name="requested_by" placeholder="Ответственное лицо / заявитель" value="{user['full_name']}" required>
            <input type="text" name="requester_position" placeholder="Должность">
            <select name="object_id" required>
                <option value="">Объект, где нужна заправка</option>
                {object_options}
            </select>
            <input type="text" name="project_name" placeholder="Проект">
            <select name="vehicle_id" required>
                <option value="">Транспорт</option>
                {vehicle_options}
            </select>
            <input type="number" step="0.01" name="requested_liters" placeholder="Запрошено литров" required>
            <textarea name="request_comment" placeholder="Комментарий заявителя"></textarea>
            <button type="submit">Создать заявку</button>
        </form>
    </div>

    <script>
    function filterByCompany(companyId) {{
        if (!companyId) return;
        window.location = "{url_for('new_request_page')}?company_id=" + encodeURIComponent(companyId);
    }}
    </script>
    """
    return render_page("Новая заявка", content)


# =========================
# REQUESTS LIST
# =========================
@app.route("/requests")
@login_required
def requests_page():
    user = current_user()

    base_query = """
        SELECT
            fr.*,
            rc.name AS requester_company_name,
            o.name AS object_name,
            v.brand,
            v.vehicle_type,
            v.plate_number
        FROM fuel_requests fr
        LEFT JOIN companies rc ON fr.requester_company_id = rc.id
        LEFT JOIN objects o ON fr.object_id = o.id
        LEFT JOIN vehicles v ON fr.vehicle_id = v.id
    """
    params = ()

    if user["role"] != "admin":
        if user["role"] == "requester":
            base_query += " WHERE fr.requester_company_id = %s "
            params = (user["company_id"],)
        elif user["role"] == "approver":
            base_query += " WHERE fr.status = 'new' "
        elif user["role"] == "fueler":
            base_query += " WHERE fr.status = 'approved' "
        elif user["role"] == "controller":
            base_query += " WHERE fr.status = 'fueled' "

    base_query += " ORDER BY fr.id DESC "

    rows_data = fetch_all(base_query, params)

    rows = ""
    for r in rows_data:
        actions = [f'<a class="btn btn-view" href="/requests/view/{r["id"]}">Открыть</a>']

        if r["status"] == "new" and user["role"] in ["admin", "approver"]:
            actions.append(f'<a class="btn btn-approve" href="/requests/approve/{r["id"]}">Рассмотреть</a>')
        if r["status"] == "approved" and user["role"] in ["admin", "fueler"]:
            actions.append(f'<a class="btn btn-fuel" href="/requests/fuel/{r["id"]}">Заправить</a>')
        if r["status"] == "fueled" and user["role"] in ["admin", "controller"]:
            actions.append(f'<a class="btn btn-check" href="/requests/check/{r["id"]}">Проверить</a>')

        rows += f"""
        <tr>
            <td>{r['id']}</td>
            <td>{status_badge(r['status'])}</td>
            <td>{r['requester_company_name'] or ''}</td>
            <td>{r['requested_by'] or ''}</td>
            <td>{r['object_name'] or ''}</td>
            <td>{r['project_name'] or ''}</td>
            <td>{r['fuel_supplier'] or ''}</td>
            <td>{(r['brand'] or '')} / {(r['vehicle_type'] or '')} / {(r['plate_number'] or '')}</td>
            <td>{r['requested_liters']}</td>
            <td><div class="actions">{''.join(actions)}</div></td>
        </tr>
        """

    content = f"""
    <div class="card">
        <h3>Список заявок</h3>
        <table>
            <tr>
                <th>ID</th>
                <th>Статус</th>
                <th>Компания-заявитель</th>
                <th>Ответственное лицо</th>
                <th>Объект</th>
                <th>Проект</th>
                <th>Кто дает дизель</th>
                <th>Транспорт</th>
                <th>Запрошено</th>
                <th>Действия</th>
            </tr>
            {rows}
        </table>
    </div>
    """
    return render_page("Заявки", content)


# =========================
# VIEW REQUEST
# =========================
@app.route("/requests/view/<int:request_id>")
@login_required
def view_request(request_id):
    r = fetch_one("""
        SELECT
            fr.*,
            rc.name AS requester_company_name,
            o.name AS object_name,
            oc.name AS object_company_name,
            v.brand,
            v.vehicle_type,
            v.plate_number,
            vc.name AS vehicle_company_name
        FROM fuel_requests fr
        LEFT JOIN companies rc ON fr.requester_company_id = rc.id
        LEFT JOIN objects o ON fr.object_id = o.id
        LEFT JOIN companies oc ON o.company_id = oc.id
        LEFT JOIN vehicles v ON fr.vehicle_id = v.id
        LEFT JOIN companies vc ON v.company_id = vc.id
        WHERE fr.id = %s
    """, (request_id,))
    if not r:
        flash("Заявка не найдена.", "error")
        return redirect(url_for("requests_page"))

    content = f"""
    <div class="card">
        <h3>Заявка №{r['id']}</h3>
        <p><b>Статус:</b> {status_badge(r['status'])}</p>
        <hr>
        <p><b>Компания-заявитель:</b> {r['requester_company_name'] or ''}</p>
        <p><b>Ответственное лицо:</b> {r['requested_by'] or ''}</p>
        <p><b>Должность:</b> {r['requester_position'] or ''}</p>
        <p><b>Объект заправки:</b> {r['object_name'] or ''}</p>
        <p><b>Компания объекта:</b> {r['object_company_name'] or ''}</p>
        <p><b>Проект:</b> {r['project_name'] or ''}</p>
        <p><b>Транспорт:</b> {(r['brand'] or '')} / {(r['vehicle_type'] or '')} / {(r['plate_number'] or '')}</p>
        <p><b>Компания транспорта:</b> {r['vehicle_company_name'] or ''}</p>
        <p><b>Запрошено литров:</b> {r['requested_liters']}</p>
        <p><b>Комментарий заявителя:</b> {r['request_comment'] or ''}</p>
        <p><b>Дата заявки:</b> {r['created_at']}</p>
        <hr>
        <p><b>Разрешено литров:</b> {r['approved_liters'] if r['approved_liters'] is not None else ''}</p>
        <p><b>Кто разрешил:</b> {r['approved_by'] or ''}</p>
        <p><b>Дизель обеспечивает:</b> {r['fuel_supplier'] or ''}</p>
        <p><b>Комментарий руководителя:</b> {r['approval_comment'] or ''}</p>
        <p><b>Дата решения:</b> {r['approved_at'] or ''}</p>
        <hr>
        <p><b>Фактически заправлено:</b> {r['actual_liters'] if r['actual_liters'] is not None else ''}</p>
        <p><b>Спидометр:</b> {r['speedometer'] if r['speedometer'] is not None else ''}</p>
        <p><b>Заправщик:</b> {r['fueler_name'] or ''}</p>
        <p><b>Комментарий заправщика:</b> {r['fueling_comment'] or ''}</p>
        <p><b>Дата заправки:</b> {r['fueled_at'] or ''}</p>
        <hr>
        <p><b>Контролер:</b> {r['controller_name'] or ''}</p>
        <p><b>Комментарий контролера:</b> {r['control_comment'] or ''}</p>
        <p><b>Дата проверки:</b> {r['checked_at'] or ''}</p>
        <br>
        <a class="btn btn-back" href="{url_for('requests_page')}">Назад</a>
    </div>
    """
    return render_page(f"Заявка №{request_id}", content)


# =========================
# APPROVE
# =========================
@app.route("/requests/approve/<int:request_id>", methods=["GET", "POST"])
@login_required
@role_required("admin", "approver")
def approve_request(request_id):
    r = fetch_one("""
        SELECT
            fr.*,
            rc.name AS requester_company_name,
            o.name AS object_name,
            v.brand,
            v.vehicle_type,
            v.plate_number
        FROM fuel_requests fr
        LEFT JOIN companies rc ON fr.requester_company_id = rc.id
        LEFT JOIN objects o ON fr.object_id = o.id
        LEFT JOIN vehicles v ON fr.vehicle_id = v.id
        WHERE fr.id = %s
    """, (request_id,))
    if not r:
        flash("Заявка не найдена.", "error")
        return redirect(url_for("requests_page"))

    if r["status"] != "new":
        flash("Рассмотреть можно только новую заявку.", "error")
        return redirect(url_for("requests_page"))

    if request.method == "POST":
        action = request.form.get("action")
        approved_by = request.form.get("approved_by", "").strip()
        approval_comment = request.form.get("approval_comment", "").strip()
        approved_liters = request.form.get("approved_liters", "").strip()
        fuel_supplier = request.form.get("fuel_supplier", "").strip()

        if not approved_by:
            flash("Укажите, кто рассматривает заявку.", "error")
            return redirect(url_for("approve_request", request_id=request_id))

        if action == "reject":
            execute_query("""
                UPDATE fuel_requests
                SET status='rejected',
                    approved_by=%s,
                    approval_comment=%s,
                    approved_at=CURRENT_TIMESTAMP
                WHERE id=%s
            """, (approved_by, approval_comment, request_id))
            flash("Заявка отклонена.", "success")
            return redirect(url_for("requests_page"))

        if action == "approve":
            if not approved_liters or not fuel_supplier:
                flash("Укажите разрешенные литры и кто обеспечивает дизель.", "error")
                return redirect(url_for("approve_request", request_id=request_id))

            try:
                approved_liters_value = float(approved_liters)
                if approved_liters_value <= 0:
                    flash("Количество литров должно быть больше нуля.", "error")
                    return redirect(url_for("approve_request", request_id=request_id))
            except ValueError:
                flash("Неверно указано количество литров.", "error")
                return redirect(url_for("approve_request", request_id=request_id))

            execute_query("""
                UPDATE fuel_requests
                SET status='approved',
                    approved_liters=%s,
                    fuel_supplier=%s,
                    approved_by=%s,
                    approval_comment=%s,
                    approved_at=CURRENT_TIMESTAMP
                WHERE id=%s
            """, (approved_liters_value, fuel_supplier, approved_by, approval_comment, request_id))

            flash("Заявка разрешена.", "success")
            return redirect(url_for("requests_page"))

    content = f"""
    <div class="card">
        <h3>Рассмотрение заявки №{r['id']}</h3>
        <p><b>Компания-заявитель:</b> {r['requester_company_name'] or ''}</p>
        <p><b>Ответственное лицо:</b> {r['requested_by'] or ''}</p>
        <p><b>Объект:</b> {r['object_name'] or ''}</p>
        <p><b>Проект:</b> {r['project_name'] or ''}</p>
        <p><b>Транспорт:</b> {(r['brand'] or '')} / {(r['vehicle_type'] or '')} / {(r['plate_number'] or '')}</p>
        <p><b>Запрошено литров:</b> {r['requested_liters']}</p>
        <form method="POST">
            <input type="text" name="approved_by" placeholder="Кто рассматривает / разрешает" value="{current_user()['full_name']}" required>
            <input type="number" step="0.01" name="approved_liters" placeholder="Разрешено литров">
            <input type="text" name="fuel_supplier" placeholder="Кто обеспечивает дизель">
            <textarea name="approval_comment" placeholder="Комментарий руководителя"></textarea>
            <button type="submit" name="action" value="approve">Разрешить заявку</button>
            <button class="btn-red" type="submit" name="action" value="reject">Отклонить заявку</button>
        </form>
        <br>
        <a class="btn btn-back" href="{url_for('requests_page')}">Назад</a>
    </div>
    """
    return render_page(f"Рассмотрение заявки №{request_id}", content)


# =========================
# FUEL
# =========================
@app.route("/requests/fuel/<int:request_id>", methods=["GET", "POST"])
@login_required
@role_required("admin", "fueler")
def fuel_request(request_id):
    r = fetch_one("""
        SELECT
            fr.*,
            rc.name AS requester_company_name,
            o.name AS object_name,
            v.brand,
            v.vehicle_type,
            v.plate_number
        FROM fuel_requests fr
        LEFT JOIN companies rc ON fr.requester_company_id = rc.id
        LEFT JOIN objects o ON fr.object_id = o.id
        LEFT JOIN vehicles v ON fr.vehicle_id = v.id
        WHERE fr.id = %s
    """, (request_id,))
    if not r:
        flash("Заявка не найдена.", "error")
        return redirect(url_for("requests_page"))

    if r["status"] != "approved":
        flash("Заправлять можно только разрешенную заявку.", "error")
        return redirect(url_for("requests_page"))

    if request.method == "POST":
        actual_liters = request.form.get("actual_liters", "").strip()
        speedometer = request.form.get("speedometer", "").strip()
        fueler_name = request.form.get("fueler_name", "").strip()
        fueling_comment = request.form.get("fueling_comment", "").strip()

        if not actual_liters or not fueler_name:
            flash("Заполните обязательные поля.", "error")
            return redirect(url_for("fuel_request", request_id=request_id))

        try:
            actual_liters_value = float(actual_liters)
            if actual_liters_value <= 0:
                flash("Количество литров должно быть больше нуля.", "error")
                return redirect(url_for("fuel_request", request_id=request_id))
        except ValueError:
            flash("Неверно указано количество литров.", "error")
            return redirect(url_for("fuel_request", request_id=request_id))

        speedometer_value = None
        if speedometer:
            try:
                speedometer_value = int(speedometer)
            except ValueError:
                flash("Спидометр должен быть целым числом.", "error")
                return redirect(url_for("fuel_request", request_id=request_id))

        execute_query("""
            UPDATE fuel_requests
            SET status='fueled',
                actual_liters=%s,
                speedometer=%s,
                fueler_name=%s,
                fueling_comment=%s,
                fueled_at=CURRENT_TIMESTAMP
            WHERE id=%s
        """, (actual_liters_value, speedometer_value, fueler_name, fueling_comment, request_id))

        execute_query("""
            INSERT INTO fuel_transactions (
                vehicle_id, object_id, entry_type, liters, speedometer, entered_by, comment
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            r["vehicle_id"],
            r["object_id"],
            "chiqim",
            actual_liters_value,
            speedometer_value,
            fueler_name,
            f"Выдача по заявке №{request_id}. {fueling_comment}" if fueling_comment else f"Выдача по заявке №{request_id}"
        ))

        flash("Заправка сохранена.", "success")
        return redirect(url_for("requests_page"))

    content = f"""
    <div class="card">
        <h3>Заправка по заявке №{r['id']}</h3>
        <p><b>Компания-заявитель:</b> {r['requester_company_name'] or ''}</p>
        <p><b>Объект:</b> {r['object_name'] or ''}</p>
        <p><b>Проект:</b> {r['project_name'] or ''}</p>
        <p><b>Транспорт:</b> {(r['brand'] or '')} / {(r['vehicle_type'] or '')} / {(r['plate_number'] or '')}</p>
        <p><b>Разрешено литров:</b> {r['approved_liters'] if r['approved_liters'] is not None else ''}</p>
        <p><b>Дизель обеспечивает:</b> {r['fuel_supplier'] or ''}</p>
        <form method="POST">
            <input type="number" step="0.01" name="actual_liters" placeholder="Фактически заправлено литров" required>
            <input type="number" name="speedometer" placeholder="Спидометр">
            <input type="text" name="fueler_name" placeholder="Заправщик" value="{current_user()['full_name']}" required>
            <textarea name="fueling_comment" placeholder="Комментарий заправщика"></textarea>
            <button type="submit">Сохранить заправку</button>
        </form>
        <br>
        <a class="btn btn-back" href="{url_for('requests_page')}">Назад</a>
    </div>
    """
    return render_page(f"Заправка заявки №{request_id}", content)


# =========================
# CHECK
# =========================
@app.route("/requests/check/<int:request_id>", methods=["GET", "POST"])
@login_required
@role_required("admin", "controller")
def check_request(request_id):
    r = fetch_one("""
        SELECT
            fr.*,
            rc.name AS requester_company_name,
            o.name AS object_name,
            v.brand,
            v.vehicle_type,
            v.plate_number
        FROM fuel_requests fr
        LEFT JOIN companies rc ON fr.requester_company_id = rc.id
        LEFT JOIN objects o ON fr.object_id = o.id
        LEFT JOIN vehicles v ON fr.vehicle_id = v.id
        WHERE fr.id = %s
    """, (request_id,))
    if not r:
        flash("Заявка не найдена.", "error")
        return redirect(url_for("requests_page"))

    if r["status"] != "fueled":
        flash("Проверить можно только заправленную заявку.", "error")
        return redirect(url_for("requests_page"))

    if request.method == "POST":
        controller_name = request.form.get("controller_name", "").strip()
        control_comment = request.form.get("control_comment", "").strip()

        if not controller_name:
            flash("Укажите контролера.", "error")
            return redirect(url_for("check_request", request_id=request_id))

        execute_query("""
            UPDATE fuel_requests
            SET status='checked',
                controller_name=%s,
                control_comment=%s,
                checked_at=CURRENT_TIMESTAMP
            WHERE id=%s
        """, (controller_name, control_comment, request_id))

        flash("Заявка проверена и завершена.", "success")
        return redirect(url_for("requests_page"))

    content = f"""
    <div class="card">
        <h3>Проверка заявки №{r['id']}</h3>
        <p><b>Компания-заявитель:</b> {r['requester_company_name'] or ''}</p>
        <p><b>Объект:</b> {r['object_name'] or ''}</p>
        <p><b>Проект:</b> {r['project_name'] or ''}</p>
        <p><b>Транспорт:</b> {(r['brand'] or '')} / {(r['vehicle_type'] or '')} / {(r['plate_number'] or '')}</p>
        <p><b>Запрошено:</b> {r['requested_liters']}</p>
        <p><b>Разрешено:</b> {r['approved_liters'] if r['approved_liters'] is not None else ''}</p>
        <p><b>Фактически заправлено:</b> {r['actual_liters'] if r['actual_liters'] is not None else ''}</p>
        <p><b>Дизель обеспечивает:</b> {r['fuel_supplier'] or ''}</p>
        <p><b>Спидометр:</b> {r['speedometer'] if r['speedometer'] is not None else ''}</p>
        <form method="POST">
            <input type="text" name="controller_name" placeholder="Контролер" value="{current_user()['full_name']}" required>
            <textarea name="control_comment" placeholder="Комментарий контролера"></textarea>
            <button type="submit">Завершить проверку</button>
        </form>
        <br>
        <a class="btn btn-back" href="{url_for('requests_page')}">Назад</a>
    </div>
    """
    return render_page(f"Проверка заявки №{request_id}", content)


# =========================
# JOURNAL
# =========================
@app.route("/transactions")
@login_required
def transactions_page():
    user = current_user()

    query = """
        SELECT
            ft.id,
            ft.entry_type,
            ft.liters,
            ft.speedometer,
            ft.entered_by,
            ft.comment,
            ft.created_at,
            v.brand,
            v.vehicle_type,
            v.plate_number,
            o.name AS object_name
        FROM fuel_transactions ft
        LEFT JOIN vehicles v ON ft.vehicle_id = v.id
        LEFT JOIN objects o ON ft.object_id = o.id
    """
    params = ()

    if user["role"] != "admin" and user["company_id"]:
        query += """
            WHERE o.company_id = %s
        """
        params = (user["company_id"],)

    query += " ORDER BY ft.id DESC "

    transactions = fetch_all(query, params)

    rows = ""
    for t in transactions:
        entry_type_ru = "Приход" if t["entry_type"] == "kirim" else "Расход"
        rows += f"""
        <tr>
            <td>{t['id']}</td>
            <td>{t['object_name'] or ''}</td>
            <td>{(t['brand'] or '')} / {(t['vehicle_type'] or '')} / {(t['plate_number'] or '')}</td>
            <td>{entry_type_ru}</td>
            <td>{t['liters']}</td>
            <td>{t['speedometer'] if t['speedometer'] is not None else ''}</td>
            <td>{t['entered_by'] or ''}</td>
            <td>{t['comment'] or ''}</td>
            <td>{t['created_at']}</td>
            <td>
                {"<a class='btn btn-delete' href='/transactions/delete/" + str(t["id"]) + "' onclick=\"return confirm('Удалить запись?')\">Удалить</a>" if user["role"] == "admin" else ""}
            </td>
        </tr>
        """

    content = f"""
    <div class="card">
        <h3>Журнал операций ГСМ</h3>
        <table>
            <tr>
                <th>ID</th>
                <th>Объект</th>
                <th>Транспорт</th>
                <th>Тип</th>
                <th>Литры</th>
                <th>Спидометр</th>
                <th>Кто ввел</th>
                <th>Комментарий</th>
                <th>Дата</th>
                <th>Действие</th>
            </tr>
            {rows}
        </table>
    </div>
    """
    return render_page("Журнал ГСМ", content)


@app.route("/transactions/delete/<int:tx_id>")
@login_required
@role_required("admin")
def delete_transaction(tx_id):
    execute_query("DELETE FROM fuel_transactions WHERE id=%s", (tx_id,))
    flash("Запись удалена.", "success")
    return redirect(url_for("transactions_page"))


# =========================
# START
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
