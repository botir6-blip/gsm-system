import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, request, redirect, url_for, render_template_string, flash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "supersecretkey")

DATABASE_URL = os.environ.get("DATABASE_URL")


# =========================
# DATABASE
# =========================
def get_connection():
    return psycopg2.connect(DATABASE_URL, sslmode="require")


def normalize_plate(plate: str) -> str:
    if not plate:
        return ""
    return "".join(ch for ch in plate.upper() if ch.isalnum())


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

    # fuel_transactions
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

    # ===== MIGRATIONS =====
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

    # fill normalized plates if empty
    cur.execute("SELECT id, plate_number FROM vehicles WHERE plate_number_normalized IS NULL OR plate_number_normalized = ''")
    for row in cur.fetchall():
        vehicle_id, plate_number = row
        cur.execute("""
            UPDATE vehicles
            SET plate_number_normalized = %s
            WHERE id = %s
        """, (normalize_plate(plate_number), vehicle_id))

    # unique index on normalized plate
    if not index_exists(cur, "idx_vehicles_plate_number_normalized_unique"):
        cur.execute("""
            SELECT plate_number_normalized, COUNT(*)
            FROM vehicles
            WHERE plate_number_normalized IS NOT NULL
            GROUP BY plate_number_normalized
            HAVING COUNT(*) > 1
        """)
        duplicates = cur.fetchall()

        # if duplicates exist, skip unique index creation to avoid crash
        if not duplicates:
            cur.execute("""
                CREATE UNIQUE INDEX idx_vehicles_plate_number_normalized_unique
                ON vehicles (plate_number_normalized)
            """)

    # unique constraint for objects(name, company_id) if missing
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


# IMPORTANT: call after function definition
init_db()


# =========================
# HELPERS
# =========================
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


def render_page(title, content):
    return render_template_string(BASE_HTML, title=title, content=content)


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
            background: #f5f7fb;
            margin: 0;
            padding: 20px;
        }
        .container {
            max-width: 1250px;
            margin: auto;
            background: white;
            padding: 20px;
            border-radius: 14px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.08);
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
        }
        .menu a:hover {
            background: #1d4ed8;
        }
        form {
            display: grid;
            gap: 12px;
            margin-bottom: 25px;
        }
        input, select, textarea, button {
            padding: 10px;
            border-radius: 10px;
            border: 1px solid #d1d5db;
            font-size: 15px;
        }
        button {
            background: #16a34a;
            color: white;
            border: none;
            cursor: pointer;
        }
        button:hover {
            background: #15803d;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
            background: white;
        }
        th, td {
            border: 1px solid #e5e7eb;
            padding: 10px;
            text-align: left;
            vertical-align: top;
        }
        th {
            background: #f3f4f6;
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
        .two-col {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }
        .card {
            background: #f9fafb;
            border: 1px solid #e5e7eb;
            padding: 16px;
            border-radius: 12px;
        }
        .actions {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
        }
        .btn-edit, .btn-delete, .btn-back {
            padding: 6px 10px;
            color: white;
            border-radius: 8px;
            text-decoration: none;
            font-size: 13px;
            display: inline-block;
        }
        .btn-edit {
            background: #f59e0b;
        }
        .btn-edit:hover {
            background: #d97706;
        }
        .btn-delete {
            background: #dc2626;
        }
        .btn-delete:hover {
            background: #b91c1c;
        }
        .btn-back {
            background: #6b7280;
        }
        .btn-back:hover {
            background: #4b5563;
        }
        @media (max-width: 768px) {
            .two-col {
                grid-template-columns: 1fr;
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
        <a href="{{ url_for('fuel_page') }}">Ввод ГСМ</a>
        <a href="{{ url_for('transactions_page') }}">Журнал ГСМ</a>
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


# =========================
# HOME
# =========================
@app.route("/")
def index():
    company_count = fetch_one("SELECT COUNT(*) AS cnt FROM companies")["cnt"]
    object_count = fetch_one("SELECT COUNT(*) AS cnt FROM objects")["cnt"]
    vehicle_count = fetch_one("SELECT COUNT(*) AS cnt FROM vehicles")["cnt"]
    tx_count = fetch_one("SELECT COUNT(*) AS cnt FROM fuel_transactions")["cnt"]

    content = f"""
    <div class="two-col">
        <div class="card">
            <h3>Краткая информация</h3>
            <p><b>Компании:</b> {company_count}</p>
            <p><b>Объекты:</b> {object_count}</p>
            <p><b>Транспорт:</b> {vehicle_count}</p>
            <p><b>Операции ГСМ:</b> {tx_count}</p>
        </div>
        <div class="card">
            <h3>Возможности системы</h3>
            <p>• База компаний</p>
            <p>• База объектов</p>
            <p>• База транспорта</p>
            <p>• Журнал прихода и расхода ГСМ</p>
            <p>• Учет спидометра</p>
            <p>• Защита от дубликата госномера</p>
        </div>
    </div>
    """
    return render_page("Система контроля ГСМ", content)


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
                    <a class="btn-edit" href="/companies/edit/{c['id']}">Редактировать</a>
                    <a class="btn-delete" href="/companies/delete/{c['id']}" onclick="return confirm('Удалить эту компанию?')">Удалить</a>
                </div>
            </td>
        </tr>
        """

    content = f"""
    <div class="card">
        <h3>Добавить новую компанию</h3>
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
                <th>Действие</th>
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

        execute_query(
            "UPDATE companies SET name=%s WHERE id=%s",
            (name, company_id)
        )
        flash("Компания обновлена.", "success")
        return redirect(url_for("companies_page"))

    content = f"""
    <div class="card">
        <h3>Редактировать компанию</h3>
        <form method="POST">
            <input type="text" name="name" value="{company['name']}" required>
            <button type="submit">Сохранить изменения</button>
        </form>
        <a class="btn-back" href="{url_for('companies_page')}">Назад</a>
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

    company_options = "".join(
        [f"<option value='{c['id']}'>{c['name']}</option>" for c in companies]
    )

    rows = ""
    for o in objects:
        rows += f"""
        <tr>
            <td>{o['id']}</td>
            <td>{o['name']}</td>
            <td>{o['company_name'] or ''}</td>
            <td>
                <div class="actions">
                    <a class="btn-edit" href="/objects/edit/{o['id']}">Редактировать</a>
                    <a class="btn-delete" href="/objects/delete/{o['id']}" onclick="return confirm('Удалить этот объект?')">Удалить</a>
                </div>
            </td>
        </tr>
        """

    content = f"""
    <div class="card">
        <h3>Добавить новый объект</h3>
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
                <th>Действие</th>
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
        <h3>Редактировать объект</h3>
        <form method="POST">
            <input type="text" name="name" value="{obj['name']}" required>
            <select name="company_id" required>
                <option value="">Выберите компанию</option>
                {company_options}
            </select>
            <button type="submit">Сохранить изменения</button>
        </form>
        <a class="btn-back" href="{url_for('objects_page')}">Назад</a>
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

    company_options = "".join(
        [f"<option value='{c['id']}'>{c['name']}</option>" for c in companies]
    )

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
                    <a class="btn-edit" href="/vehicles/edit/{v['id']}">Редактировать</a>
                    <a class="btn-delete" href="/vehicles/delete/{v['id']}" onclick="return confirm('Удалить этот транспорт?')">Удалить</a>
                </div>
            </td>
        </tr>
        """

    content = f"""
    <div class="card">
        <h3>Добавить новый транспорт</h3>
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
                <th>Действие</th>
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
        <h3>Редактировать транспорт</h3>
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
        <a class="btn-back" href="{url_for('vehicles_page')}">Назад</a>
    </div>
    """
    return render_page("Редактирование транспорта", content)


@app.route("/vehicles/delete/<int:vehicle_id>")
def delete_vehicle(vehicle_id):
    execute_query("DELETE FROM vehicles WHERE id=%s", (vehicle_id,))
    flash("Транспорт удален.", "success")
    return redirect(url_for("vehicles_page"))


# =========================
# FUEL ENTRY
# =========================
@app.route("/fuel", methods=["GET", "POST"])
def fuel_page():
    if request.method == "POST":
        vehicle_id = request.form.get("vehicle_id")
        object_id = request.form.get("object_id")
        entry_type = request.form.get("entry_type")
        liters = request.form.get("liters", "").strip()
        speedometer = request.form.get("speedometer", "").strip()
        entered_by = request.form.get("entered_by", "").strip()
        comment = request.form.get("comment", "").strip()

        if not vehicle_id or not object_id or not entry_type or not liters:
            flash("Заполните обязательные поля.", "error")
            return redirect(url_for("fuel_page"))

        try:
            liters_value = float(liters)
            if liters_value <= 0:
                flash("Количество литров должно быть больше нуля.", "error")
                return redirect(url_for("fuel_page"))
        except ValueError:
            flash("Неверно указано количество литров.", "error")
            return redirect(url_for("fuel_page"))

        speedometer_value = None
        if speedometer:
            try:
                speedometer_value = int(speedometer)
            except ValueError:
                flash("Показание спидометра должно быть целым числом.", "error")
                return redirect(url_for("fuel_page"))

        execute_query("""
            INSERT INTO fuel_transactions (
                vehicle_id, object_id, entry_type, liters, speedometer, entered_by, comment
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            vehicle_id, object_id, entry_type, liters_value, speedometer_value, entered_by, comment
        ))

        flash("Операция ГСМ сохранена.", "success")
        return redirect(url_for("fuel_page"))

    vehicles = fetch_all("""
        SELECT v.id, v.brand, v.vehicle_type, v.plate_number, c.name AS company_name
        FROM vehicles v
        LEFT JOIN companies c ON v.company_id = c.id
        ORDER BY v.brand, v.plate_number
    """)

    objects = fetch_all("""
        SELECT o.id, o.name, c.name AS company_name
        FROM objects o
        LEFT JOIN companies c ON o.company_id = c.id
        ORDER BY o.name
    """)

    vehicle_options = "".join([
        f"<option value='{v['id']}'>{v['brand']} / {v['vehicle_type']} / {v['plate_number']} / {v['company_name'] or ''}</option>"
        for v in vehicles
    ])

    object_options = "".join([
        f"<option value='{o['id']}'>{o['name']} / {o['company_name'] or ''}</option>"
        for o in objects
    ])

    content = f"""
    <div class="card">
        <h3>Ввод ГСМ</h3>
        <form method="POST">
            <select name="object_id" required>
                <option value="">Выберите объект</option>
                {object_options}
            </select>

            <select name="vehicle_id" required>
                <option value="">Выберите транспорт</option>
                {vehicle_options}
            </select>

            <select name="entry_type" required>
                <option value="">Выберите тип операции</option>
                <option value="kirim">Приход</option>
                <option value="chiqim">Расход</option>
            </select>

            <input type="number" step="0.01" name="liters" placeholder="Количество литров" required>
            <input type="number" name="speedometer" placeholder="Спидометр">
            <input type="text" name="entered_by" placeholder="Кто ввел">
            <textarea name="comment" placeholder="Комментарий"></textarea>
            <button type="submit">Сохранить</button>
        </form>
    </div>
    """
    return render_page("Ввод ГСМ", content)


# =========================
# TRANSACTIONS
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
            o.name AS object_name,
            c.name AS company_name
        FROM fuel_transactions ft
        LEFT JOIN vehicles v ON ft.vehicle_id = v.id
        LEFT JOIN objects o ON ft.object_id = o.id
        LEFT JOIN companies c ON o.company_id = c.id
        ORDER BY ft.id DESC
    """)

    rows = ""
    for t in transactions:
        entry_type_ru = "Приход" if t["entry_type"] == "kirim" else "Расход"

        rows += f"""
        <tr>
            <td>{t['id']}</td>
            <td>{t['object_name'] or ''}</td>
            <td>{t['company_name'] or ''}</td>
            <td>{(t['brand'] or '')} / {(t['vehicle_type'] or '')} / {(t['plate_number'] or '')}</td>
            <td>{entry_type_ru}</td>
            <td>{t['liters']}</td>
            <td>{t['speedometer'] if t['speedometer'] is not None else ''}</td>
            <td>{t['entered_by'] or ''}</td>
            <td>{t['comment'] or ''}</td>
            <td>{t['created_at']}</td>
            <td>
                <a class="btn-delete" href="/transactions/delete/{t['id']}" onclick="return confirm('Удалить эту операцию?')">Удалить</a>
            </td>
        </tr>
        """

    content = f"""
    <div class="card">
        <h3>Журнал ГСМ</h3>
        <table>
            <tr>
                <th>ID</th>
                <th>Объект</th>
                <th>Компания</th>
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
    flash("Операция удалена.", "success")
    return redirect(url_for("transactions_page"))


# =========================
# START
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
