import os
import psycopg
from psycopg.rows import dict_row
from flask import Flask, request, redirect, url_for, render_template_string, flash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "supersecretkey")

DATABASE_URL = os.environ.get("DATABASE_URL")


# =========================
# DB
# =========================
def get_connection():
    return psycopg.connect(DATABASE_URL, sslmode="require", row_factory=dict_row)


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


def execute_returning_id(query, params=None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(query, params or ())
    new_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return new_id


def column_exists(cur, table_name, column_name):
    cur.execute("""
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
    """, (table_name, column_name))
    return cur.fetchone() is not None


def table_exists(cur, table_name):
    cur.execute("""
        SELECT 1
        FROM information_schema.tables
        WHERE table_name = %s
    """, (table_name,))
    return cur.fetchone() is not None


def index_exists(cur, index_name):
    cur.execute("""
        SELECT 1
        FROM pg_indexes
        WHERE indexname = %s
    """, (index_name,))
    return cur.fetchone() is not None


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    # ========= companies =========
    cur.execute("""
    CREATE TABLE IF NOT EXISTS companies (
        id SERIAL PRIMARY KEY,
        name VARCHAR(150) NOT NULL UNIQUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # ========= objects =========
    cur.execute("""
    CREATE TABLE IF NOT EXISTS objects (
        id SERIAL PRIMARY KEY,
        name VARCHAR(150) NOT NULL,
        company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # ========= vehicles =========
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

    # ========= requests =========
    cur.execute("""
    CREATE TABLE IF NOT EXISTS fuel_requests (
        id SERIAL PRIMARY KEY,
        company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
        object_id INTEGER REFERENCES objects(id) ON DELETE SET NULL,
        vehicle_id INTEGER REFERENCES vehicles(id) ON DELETE SET NULL,

        requested_liters NUMERIC(10,2) NOT NULL DEFAULT 0,
        approved_liters NUMERIC(10,2),
        actual_liters NUMERIC(10,2),

        speedometer INTEGER,

        requested_by VARCHAR(100),
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

    # ========= old transactions table =========
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

    # ========= migrations =========
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

    # fill normalized values
    cur.execute("""
        SELECT id, plate_number
        FROM vehicles
        WHERE plate_number_normalized IS NULL OR plate_number_normalized = ''
    """)
    for row in cur.fetchall():
        vehicle_id, plate_number = row
        cur.execute("""
            UPDATE vehicles
            SET plate_number_normalized = %s
            WHERE id = %s
        """, (normalize_plate(plate_number), vehicle_id))

    # unique index for normalized plate if possible
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

    # unique for objects by (name, company_id) if possible
    cur.execute("""
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'objects_name_company_unique'
    """)
    if not cur.fetchone():
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


init_db()


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
            background: #f3f6fb;
            margin: 0;
            padding: 20px;
        }
        .container {
            max-width: 1280px;
            margin: auto;
            background: #ffffff;
            padding: 22px;
            border-radius: 16px;
            box-shadow: 0 8px 24px rgba(0,0,0,0.08);
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
        }
        .menu a:hover {
            background: #1d4ed8;
        }
        .grid-2 {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 18px;
        }
        .card {
            background: #f9fafb;
            border: 1px solid #e5e7eb;
            padding: 18px;
            border-radius: 14px;
            margin-bottom: 18px;
        }
        form {
            display: grid;
            gap: 12px;
        }
        input, select, textarea, button {
            padding: 12px;
            border-radius: 10px;
            border: 1px solid #cfd6df;
            font-size: 15px;
            box-sizing: border-box;
            width: 100%;
        }
        textarea {
            min-height: 90px;
            resize: vertical;
        }
        button {
            background: #16a34a;
            color: white;
            border: none;
            cursor: pointer;
            font-weight: bold;
        }
        button:hover {
            background: #15803d;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
            background: white;
            font-size: 14px;
        }
        th, td {
            border: 1px solid #e5e7eb;
            padding: 10px;
            text-align: left;
            vertical-align: top;
        }
        th {
            background: #eef2f7;
        }
        .flash {
            padding: 12px;
            border-radius: 10px;
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
            border-radius: 8px;
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

        @media (max-width: 900px) {
            .grid-2 {
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
    <h1>{{ title }}</h1>

    <div class="menu">
        <a href="{{ url_for('index') }}">Главная</a>
        <a href="{{ url_for('companies_page') }}">Компании</a>
        <a href="{{ url_for('objects_page') }}">Объекты</a>
        <a href="{{ url_for('vehicles_page') }}">Транспорт</a>
        <a href="{{ url_for('new_request_page') }}">Новая заявка</a>
        <a href="{{ url_for('requests_page') }}">Заявки</a>
        <a href="{{ url_for('transactions_page') }}">Журнал</a>
    </div>

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
    return render_template_string(BASE_HTML, title=title, content=content)


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
# HOME
# =========================
@app.route("/")
def index():
    company_count = fetch_one("SELECT COUNT(*) AS cnt FROM companies")["cnt"]
    object_count = fetch_one("SELECT COUNT(*) AS cnt FROM objects")["cnt"]
    vehicle_count = fetch_one("SELECT COUNT(*) AS cnt FROM vehicles")["cnt"]
    request_count = fetch_one("SELECT COUNT(*) AS cnt FROM fuel_requests")["cnt"]

    new_count = fetch_one("SELECT COUNT(*) AS cnt FROM fuel_requests WHERE status='new'")["cnt"]
    approved_count = fetch_one("SELECT COUNT(*) AS cnt FROM fuel_requests WHERE status='approved'")["cnt"]
    fueled_count = fetch_one("SELECT COUNT(*) AS cnt FROM fuel_requests WHERE status='fueled'")["cnt"]
    checked_count = fetch_one("SELECT COUNT(*) AS cnt FROM fuel_requests WHERE status='checked'")["cnt"]

    content = f"""
    <div class="grid-2">
        <div class="card">
            <h3>Справочники</h3>
            <p><b>Компании:</b> {company_count}</p>
            <p><b>Объекты:</b> {object_count}</p>
            <p><b>Транспорт:</b> {vehicle_count}</p>
        </div>
        <div class="card">
            <h3>Заявки на ГСМ</h3>
            <p><b>Всего заявок:</b> {request_count}</p>
            <p><b>Новые:</b> {new_count}</p>
            <p><b>Разрешенные:</b> {approved_count}</p>
            <p><b>Заправленные:</b> {fueled_count}</p>
            <p><b>Проверенные:</b> {checked_count}</p>
        </div>
    </div>

    <div class="card">
        <h3>Логика работы</h3>
        <p>1. Заявитель создает заявку</p>
        <p>2. Ответственный руководитель разрешает или отклоняет заявку</p>
        <p>3. Заправщик вводит фактически выданное количество топлива</p>
        <p>4. Контролер проверяет и завершает операцию</p>
    </div>
    """
    return render_page("Система заявок и контроля ГСМ", content)


# =========================
# COMPANIES
# =========================
@app.route("/companies", methods=["GET", "POST"])
def companies_page():
    if request.method == "POST":
        name = request.form.get("name", "").strip()

        if not name:
            flash("Введите название компании.", "error")
            return redirect(url_for("companies_page"))

        existing = fetch_one(
            "SELECT * FROM companies WHERE LOWER(name)=LOWER(%s)",
            (name,)
        )
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
            <tr>
                <th>ID</th>
                <th>Название</th>
                <th>Действия</th>
            </tr>
            {rows}
        </table>
    </div>
    """
    return render_page("Компании", content)


@app.route("/companies/edit/<int:company_id>", methods=["GET", "POST"])
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

        existing = fetch_one(
            "SELECT * FROM companies WHERE LOWER(name)=LOWER(%s) AND id<>%s",
            (name, company_id)
        )
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
def delete_company(company_id):
    execute_query("DELETE FROM companies WHERE id=%s", (company_id,))
    flash("Компания удалена.", "success")
    return redirect(url_for("companies_page"))


# =========================
# OBJECTS
# =========================
@app.route("/objects", methods=["GET", "POST"])
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

        execute_query(
            "INSERT INTO objects (name, company_id) VALUES (%s, %s)",
            (name, company_id)
        )
        flash("Объект добавлен.", "success")
        return redirect(url_for("objects_page"))

    companies = fetch_all("SELECT * FROM companies ORDER BY name")
    objects = fetch_all("""
        SELECT o.id, o.name, c.name AS company_name
        FROM objects o
        LEFT JOIN companies c ON o.company_id = c.id
        ORDER BY o.id DESC
    """)

    company_options = "".join([
        f"<option value='{c['id']}'>{c['name']}</option>"
        for c in companies
    ])

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
            <tr>
                <th>ID</th>
                <th>Объект</th>
                <th>Компания</th>
                <th>Действия</th>
            </tr>
            {rows}
        </table>
    </div>
    """
    return render_page("Объекты", content)


@app.route("/objects/edit/<int:object_id>", methods=["GET", "POST"])
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

        execute_query("""
            UPDATE objects
            SET name=%s, company_id=%s
            WHERE id=%s
        """, (name, company_id, object_id))

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
def delete_object(object_id):
    execute_query("DELETE FROM objects WHERE id=%s", (object_id,))
    flash("Объект удален.", "success")
    return redirect(url_for("objects_page"))


# =========================
# VEHICLES
# =========================
@app.route("/vehicles", methods=["GET", "POST"])
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

        existing = fetch_one("""
            SELECT * FROM vehicles
            WHERE plate_number_normalized=%s
        """, (normalized,))
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

    company_options = "".join([
        f"<option value='{c['id']}'>{c['name']}</option>"
        for c in companies
    ])

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
            <tr>
                <th>ID</th>
                <th>Марка</th>
                <th>Тип</th>
                <th>Гос. номер</th>
                <th>Компания</th>
                <th>Действия</th>
            </tr>
            {rows}
        </table>
    </div>
    """
    return render_page("Транспорт", content)


@app.route("/vehicles/edit/<int:vehicle_id>", methods=["GET", "POST"])
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
            SET brand=%s,
                vehicle_type=%s,
                plate_number=%s,
                plate_number_normalized=%s,
                company_id=%s
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
def delete_vehicle(vehicle_id):
    execute_query("DELETE FROM vehicles WHERE id=%s", (vehicle_id,))
    flash("Транспорт удален.", "success")
    return redirect(url_for("vehicles_page"))


# =========================
# NEW REQUEST
# =========================
@app.route("/requests/new", methods=["GET", "POST"])
def new_request_page():
    if request.method == "POST":
        company_id = request.form.get("company_id")
        object_id = request.form.get("object_id")
        vehicle_id = request.form.get("vehicle_id")
        requested_liters = request.form.get("requested_liters", "").strip()
        requested_by = request.form.get("requested_by", "").strip()
        request_comment = request.form.get("request_comment", "").strip()

        if not company_id or not object_id or not vehicle_id or not requested_liters or not requested_by:
            flash("Заполните обязательные поля.", "error")
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
                company_id, object_id, vehicle_id,
                requested_liters, requested_by, request_comment, status
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'new')
        """, (company_id, object_id, vehicle_id, liters_value, requested_by, request_comment))

        flash("Заявка создана.", "success")
        return redirect(url_for("requests_page"))

    companies = fetch_all("SELECT * FROM companies ORDER BY name")
    objects = fetch_all("""
        SELECT o.id, o.name, c.name AS company_name
        FROM objects o
        LEFT JOIN companies c ON o.company_id = c.id
        ORDER BY c.name, o.name
    """)
    vehicles = fetch_all("""
        SELECT v.id, v.brand, v.vehicle_type, v.plate_number, c.name AS company_name
        FROM vehicles v
        LEFT JOIN companies c ON v.company_id = c.id
        ORDER BY c.name, v.brand, v.plate_number
    """)

    company_options = "".join([
        f"<option value='{c['id']}'>{c['name']}</option>"
        for c in companies
    ])

    object_options = "".join([
        f"<option value='{o['id']}'>{o['name']} / {o['company_name'] or ''}</option>"
        for o in objects
    ])

    vehicle_options = "".join([
        f"<option value='{v['id']}'>{v['brand']} / {v['vehicle_type']} / {v['plate_number']} / {v['company_name'] or ''}</option>"
        for v in vehicles
    ])

    content = f"""
    <div class="card">
        <h3>Новая заявка на ГСМ</h3>
        <form method="POST">
            <select name="company_id" required>
                <option value="">Выберите компанию</option>
                {company_options}
            </select>

            <select name="object_id" required>
                <option value="">Выберите объект</option>
                {object_options}
            </select>

            <select name="vehicle_id" required>
                <option value="">Выберите транспорт</option>
                {vehicle_options}
            </select>

            <input type="number" step="0.01" name="requested_liters" placeholder="Запрошено литров" required>
            <input type="text" name="requested_by" placeholder="Заявитель" required>
            <textarea name="request_comment" placeholder="Комментарий к заявке"></textarea>
            <button type="submit">Создать заявку</button>
        </form>
    </div>
    """
    return render_page("Новая заявка", content)


# =========================
# REQUESTS LIST
# =========================
@app.route("/requests")
def requests_page():
    rows_data = fetch_all("""
        SELECT
            fr.*,
            c.name AS company_name,
            o.name AS object_name,
            v.brand,
            v.vehicle_type,
            v.plate_number
        FROM fuel_requests fr
        LEFT JOIN companies c ON fr.company_id = c.id
        LEFT JOIN objects o ON fr.object_id = o.id
        LEFT JOIN vehicles v ON fr.vehicle_id = v.id
        ORDER BY fr.id DESC
    """)

    rows = ""
    for r in rows_data:
        actions = [f'<a class="btn btn-view" href="/requests/view/{r["id"]}">Открыть</a>']

        if r["status"] == "new":
            actions.append(f'<a class="btn btn-approve" href="/requests/approve/{r["id"]}">Разрешить</a>')
        if r["status"] == "approved":
            actions.append(f'<a class="btn btn-fuel" href="/requests/fuel/{r["id"]}">Заправить</a>')
        if r["status"] == "fueled":
            actions.append(f'<a class="btn btn-check" href="/requests/check/{r["id"]}">Проверить</a>')

        rows += f"""
        <tr>
            <td>{r['id']}</td>
            <td>{status_badge(r['status'])}</td>
            <td>{r['company_name'] or ''}</td>
            <td>{r['object_name'] or ''}</td>
            <td>{(r['brand'] or '')} / {(r['vehicle_type'] or '')} / {(r['plate_number'] or '')}</td>
            <td>{r['requested_liters']}</td>
            <td>{r['requested_by'] or ''}</td>
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
                <th>Компания</th>
                <th>Объект</th>
                <th>Транспорт</th>
                <th>Запрошено</th>
                <th>Заявитель</th>
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
def view_request(request_id):
    r = fetch_one("""
        SELECT
            fr.*,
            c.name AS company_name,
            o.name AS object_name,
            v.brand,
            v.vehicle_type,
            v.plate_number
        FROM fuel_requests fr
        LEFT JOIN companies c ON fr.company_id = c.id
        LEFT JOIN objects o ON fr.object_id = o.id
        LEFT JOIN vehicles v ON fr.vehicle_id = v.id
        WHERE fr.id = %s
    """, (request_id,))

    if not r:
        flash("Заявка не найдена.", "error")
        return redirect(url_for("requests_page"))

    content = f"""
    <div class="card">
        <h3>Заявка №{r['id']}</h3>
        <p><b>Статус:</b> {status_badge(r['status'])}</p>
        <p><b>Компания:</b> {r['company_name'] or ''}</p>
        <p><b>Объект:</b> {r['object_name'] or ''}</p>
        <p><b>Транспорт:</b> {(r['brand'] or '')} / {(r['vehicle_type'] or '')} / {(r['plate_number'] or '')}</p>

        <hr>

        <p><b>Запрошено литров:</b> {r['requested_liters']}</p>
        <p><b>Заявитель:</b> {r['requested_by'] or ''}</p>
        <p><b>Комментарий заявителя:</b> {r['request_comment'] or ''}</p>
        <p><b>Дата заявки:</b> {r['created_at']}</p>

        <hr>

        <p><b>Разрешено литров:</b> {r['approved_liters'] if r['approved_liters'] is not None else ''}</p>
        <p><b>Кто разрешил:</b> {r['approved_by'] or ''}</p>
        <p><b>Комментарий руководителя:</b> {r['approval_comment'] or ''}</p>
        <p><b>Дата разрешения:</b> {r['approved_at'] or ''}</p>

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
        <div class="actions">
            <a class="btn btn-back" href="{url_for('requests_page')}">Назад</a>
        </div>
    </div>
    """
    return render_page(f"Заявка №{request_id}", content)


# =========================
# APPROVE REQUEST
# =========================
@app.route("/requests/approve/<int:request_id>", methods=["GET", "POST"])
def approve_request(request_id):
    r = fetch_one("""
        SELECT
            fr.*,
            c.name AS company_name,
            o.name AS object_name,
            v.brand,
            v.vehicle_type,
            v.plate_number
        FROM fuel_requests fr
        LEFT JOIN companies c ON fr.company_id = c.id
        LEFT JOIN objects o ON fr.object_id = o.id
        LEFT JOIN vehicles v ON fr.vehicle_id = v.id
        WHERE fr.id = %s
    """, (request_id,))

    if not r:
        flash("Заявка не найдена.", "error")
        return redirect(url_for("requests_page"))

    if r["status"] != "new":
        flash("Разрешить можно только новую заявку.", "error")
        return redirect(url_for("requests_page"))

    if request.method == "POST":
        action = request.form.get("action")
        approved_by = request.form.get("approved_by", "").strip()
        approval_comment = request.form.get("approval_comment", "").strip()
        approved_liters = request.form.get("approved_liters", "").strip()

        if not approved_by:
            flash("Укажите, кто принимает решение.", "error")
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
            if not approved_liters:
                flash("Укажите разрешенное количество литров.", "error")
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
                    approved_by=%s,
                    approval_comment=%s,
                    approved_at=CURRENT_TIMESTAMP
                WHERE id=%s
            """, (approved_liters_value, approved_by, approval_comment, request_id))

            flash("Заявка разрешена.", "success")
            return redirect(url_for("requests_page"))

        flash("Неизвестное действие.", "error")
        return redirect(url_for("approve_request", request_id=request_id))

    content = f"""
    <div class="card">
        <h3>Разрешение заявки №{r['id']}</h3>
        <p><b>Компания:</b> {r['company_name'] or ''}</p>
        <p><b>Объект:</b> {r['object_name'] or ''}</p>
        <p><b>Транспорт:</b> {(r['brand'] or '')} / {(r['vehicle_type'] or '')} / {(r['plate_number'] or '')}</p>
        <p><b>Запрошено литров:</b> {r['requested_liters']}</p>
        <p><b>Заявитель:</b> {r['requested_by'] or ''}</p>
        <p><b>Комментарий:</b> {r['request_comment'] or ''}</p>

        <form method="POST">
            <input type="text" name="approved_by" placeholder="Кто разрешает / отклоняет" required>
            <input type="number" step="0.01" name="approved_liters" placeholder="Разрешено литров">
            <textarea name="approval_comment" placeholder="Комментарий руководителя"></textarea>

            <button type="submit" name="action" value="approve">Разрешить заявку</button>
            <button type="submit" name="action" value="reject" style="background:#dc2626;">Отклонить заявку</button>
        </form>

        <br>
        <a class="btn btn-back" href="{url_for('requests_page')}">Назад</a>
    </div>
    """
    return render_page(f"Разрешение заявки №{request_id}", content)


# =========================
# FUEL REQUEST
# =========================
@app.route("/requests/fuel/<int:request_id>", methods=["GET", "POST"])
def fuel_request(request_id):
    r = fetch_one("""
        SELECT
            fr.*,
            c.name AS company_name,
            o.name AS object_name,
            v.brand,
            v.vehicle_type,
            v.plate_number
        FROM fuel_requests fr
        LEFT JOIN companies c ON fr.company_id = c.id
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

        # optional log into old journal
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
        <p><b>Компания:</b> {r['company_name'] or ''}</p>
        <p><b>Объект:</b> {r['object_name'] or ''}</p>
        <p><b>Транспорт:</b> {(r['brand'] or '')} / {(r['vehicle_type'] or '')} / {(r['plate_number'] or '')}</p>
        <p><b>Разрешено литров:</b> {r['approved_liters'] if r['approved_liters'] is not None else ''}</p>
        <p><b>Кто разрешил:</b> {r['approved_by'] or ''}</p>

        <form method="POST">
            <input type="number" step="0.01" name="actual_liters" placeholder="Фактически заправлено литров" required>
            <input type="number" name="speedometer" placeholder="Спидометр">
            <input type="text" name="fueler_name" placeholder="Заправщик" required>
            <textarea name="fueling_comment" placeholder="Комментарий заправщика"></textarea>
            <button type="submit">Сохранить заправку</button>
        </form>

        <br>
        <a class="btn btn-back" href="{url_for('requests_page')}">Назад</a>
    </div>
    """
    return render_page(f"Заправка заявки №{request_id}", content)


# =========================
# CHECK REQUEST
# =========================
@app.route("/requests/check/<int:request_id>", methods=["GET", "POST"])
def check_request(request_id):
    r = fetch_one("""
        SELECT
            fr.*,
            c.name AS company_name,
            o.name AS object_name,
            v.brand,
            v.vehicle_type,
            v.plate_number
        FROM fuel_requests fr
        LEFT JOIN companies c ON fr.company_id = c.id
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
        <p><b>Компания:</b> {r['company_name'] or ''}</p>
        <p><b>Объект:</b> {r['object_name'] or ''}</p>
        <p><b>Транспорт:</b> {(r['brand'] or '')} / {(r['vehicle_type'] or '')} / {(r['plate_number'] or '')}</p>
        <p><b>Запрошено:</b> {r['requested_liters']}</p>
        <p><b>Разрешено:</b> {r['approved_liters'] if r['approved_liters'] is not None else ''}</p>
        <p><b>Фактически заправлено:</b> {r['actual_liters'] if r['actual_liters'] is not None else ''}</p>
        <p><b>Спидометр:</b> {r['speedometer'] if r['speedometer'] is not None else ''}</p>
        <p><b>Заправщик:</b> {r['fueler_name'] or ''}</p>

        <form method="POST">
            <input type="text" name="controller_name" placeholder="Контролер" required>
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
def transactions_page():
    transactions = fetch_all("""
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
        ORDER BY ft.id DESC
    """)

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
                <a class="btn btn-delete" href="/transactions/delete/{t['id']}" onclick="return confirm('Удалить запись?')">Удалить</a>
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
