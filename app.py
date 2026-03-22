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
    """
    Гос.номерни нормализация қилади:
    - пробелларни олиб ташлайди
    - тире/нуқта/бошқа белгиларни олиб ташлайди
    - катта ҳарфга ўтказади
    """
    if not plate:
        return ""
    cleaned = "".join(ch for ch in plate.upper() if ch.isalnum())
    return cleaned


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    # Компаниyалар
    cur.execute("""
    CREATE TABLE IF NOT EXISTS companies (
        id SERIAL PRIMARY KEY,
        name VARCHAR(150) NOT NULL UNIQUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Объектлар
    cur.execute("""
    CREATE TABLE IF NOT EXISTS objects (
        id SERIAL PRIMARY KEY,
        name VARCHAR(150) NOT NULL,
        company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(name, company_id)
    )
    """)

    # Транспортлар
    cur.execute("""
    CREATE TABLE IF NOT EXISTS vehicles (
        id SERIAL PRIMARY KEY,
        brand VARCHAR(100) NOT NULL,
        vehicle_type VARCHAR(100) NOT NULL,
        plate_number VARCHAR(50) NOT NULL,
        plate_number_normalized VARCHAR(50) NOT NULL UNIQUE,
        company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # ГСМ операциялари
    cur.execute("""
    CREATE TABLE IF NOT EXISTS fuel_transactions (
        id SERIAL PRIMARY KEY,
        vehicle_id INTEGER REFERENCES vehicles(id) ON DELETE SET NULL,
        object_id INTEGER REFERENCES objects(id) ON DELETE SET NULL,
        entry_type VARCHAR(20) NOT NULL, -- kirim / chiqim
        liters NUMERIC(10,2) NOT NULL DEFAULT 0,
        speedometer INTEGER,
        entered_by VARCHAR(100),
        comment TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    cur.close()
    conn.close()


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


# =========================
# HTML TEMPLATE
# =========================
BASE_HTML = """
<!DOCTYPE html>
<html lang="uz">
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
            max-width: 1200px;
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
        @media (max-width: 768px) {
            .two-col {
                grid-template-columns: 1fr;
            }
        }
        .small-btn {
            padding: 6px 10px;
            background: #dc2626;
            color: white;
            border-radius: 8px;
            text-decoration: none;
            font-size: 13px;
        }
        .small-btn:hover {
            background: #b91c1c;
        }
    </style>
</head>
<body>
<div class="container">
    <h1>{{ title }}</h1>

    <div class="menu">
        <a href="{{ url_for('index') }}">Бош саҳифа</a>
        <a href="{{ url_for('companies_page') }}">Компаниялар</a>
        <a href="{{ url_for('objects_page') }}">Объектлар</a>
        <a href="{{ url_for('vehicles_page') }}">Транспортлар</a>
        <a href="{{ url_for('fuel_page') }}">ГСМ киритиш</a>
        <a href="{{ url_for('transactions_page') }}">ГСМ журнали</a>
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


# =========================
# ROUTES
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
            <h3>Қисқача маълумот</h3>
            <p><b>Компаниялар:</b> {company_count}</p>
            <p><b>Объектлар:</b> {object_count}</p>
            <p><b>Транспортлар:</b> {vehicle_count}</p>
            <p><b>ГСМ операциялари:</b> {tx_count}</p>
        </div>
        <div class="card">
            <h3>Тизим имкониятлари</h3>
            <p>• Компания базаси</p>
            <p>• Объект базаси</p>
            <p>• Транспорт базаси</p>
            <p>• ГСМ кирим-чиқим журнали</p>
            <p>• Спидометр ҳисобини сақлаш</p>
            <p>• Дубликат гос.номердан ҳимоя</p>
        </div>
    </div>
    """
    return render_page("ГСМ Назорат Тизими", content)


# =========================
# COMPANIES
# =========================
@app.route("/companies", methods=["GET", "POST"])
def companies_page():
    if request.method == "POST":
        name = request.form.get("name", "").strip()

        if not name:
            flash("Компания номини киритинг.", "error")
            return redirect(url_for("companies_page"))

        existing = fetch_one("SELECT * FROM companies WHERE LOWER(name)=LOWER(%s)", (name,))
        if existing:
            flash("Бу компания аллақачон мавжуд.", "error")
            return redirect(url_for("companies_page"))

        execute_query("INSERT INTO companies (name) VALUES (%s)", (name,))
        flash("Компания қўшилди.", "success")
        return redirect(url_for("companies_page"))

    companies = fetch_all("SELECT * FROM companies ORDER BY id DESC")

    rows = ""
    for c in companies:
        rows += f"""
        <tr>
            <td>{c['id']}</td>
            <td>{c['name']}</td>
            <td>
                <a class="small-btn" href="/companies/delete/{c['id']}" onclick="return confirm('Ростдан ҳам ўчирмоқчимисиз?')">Ўчириш</a>
            </td>
        </tr>
        """

    content = f"""
    <div class="card">
        <h3>Янги компания қўшиш</h3>
        <form method="POST">
            <input type="text" name="name" placeholder="Компания номи" required>
            <button type="submit">Сақлаш</button>
        </form>
    </div>

    <div class="card">
        <h3>Компаниялар рўйхати</h3>
        <table>
            <tr>
                <th>ID</th>
                <th>Номи</th>
                <th>Амал</th>
            </tr>
            {rows}
        </table>
    </div>
    """
    return render_page("Компаниялар", content)


@app.route("/companies/delete/<int:company_id>")
def delete_company(company_id):
    execute_query("DELETE FROM companies WHERE id=%s", (company_id,))
    flash("Компания ўчирилди.", "success")
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
            flash("Объект номи ва компанияни танланг.", "error")
            return redirect(url_for("objects_page"))

        existing = fetch_one(
            "SELECT * FROM objects WHERE LOWER(name)=LOWER(%s) AND company_id=%s",
            (name, company_id)
        )
        if existing:
            flash("Бу объект ушбу компания учун аллақачон бор.", "error")
            return redirect(url_for("objects_page"))

        execute_query(
            "INSERT INTO objects (name, company_id) VALUES (%s, %s)",
            (name, company_id)
        )
        flash("Объект қўшилди.", "success")
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
                <a class="small-btn" href="/objects/delete/{o['id']}" onclick="return confirm('Ростдан ҳам ўчирмоқчимисиз?')">Ўчириш</a>
            </td>
        </tr>
        """

    content = f"""
    <div class="card">
        <h3>Янги объект қўшиш</h3>
        <form method="POST">
            <input type="text" name="name" placeholder="Объект номи" required>
            <select name="company_id" required>
                <option value="">Компанияни танланг</option>
                {company_options}
            </select>
            <button type="submit">Сақлаш</button>
        </form>
    </div>

    <div class="card">
        <h3>Объектлар рўйхати</h3>
        <table>
            <tr>
                <th>ID</th>
                <th>Объект</th>
                <th>Компания</th>
                <th>Амал</th>
            </tr>
            {rows}
        </table>
    </div>
    """
    return render_page("Объектлар", content)


@app.route("/objects/delete/<int:object_id>")
def delete_object(object_id):
    execute_query("DELETE FROM objects WHERE id=%s", (object_id,))
    flash("Объект ўчирилди.", "success")
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
            flash("Барча майдонларни тўлдиринг.", "error")
            return redirect(url_for("vehicles_page"))

        normalized = normalize_plate(plate_number)

        existing = fetch_one(
            "SELECT * FROM vehicles WHERE plate_number_normalized=%s",
            (normalized,)
        )
        if existing:
            flash("Бу транспорт аллақачон қўшилган. Гос.номер дубликат.", "error")
            return redirect(url_for("vehicles_page"))

        execute_query("""
            INSERT INTO vehicles (brand, vehicle_type, plate_number, plate_number_normalized, company_id)
            VALUES (%s, %s, %s, %s, %s)
        """, (brand, vehicle_type, plate_number, normalized, company_id))

        flash("Транспорт қўшилди.", "success")
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
                <a class="small-btn" href="/vehicles/delete/{v['id']}" onclick="return confirm('Ростдан ҳам ўчирмоқчимисиз?')">Ўчириш</a>
            </td>
        </tr>
        """

    content = f"""
    <div class="card">
        <h3>Янги транспорт қўшиш</h3>
        <form method="POST">
            <input type="text" name="brand" placeholder="Марка автомобиля" required>
            <input type="text" name="vehicle_type" placeholder="Тип автомобиля" required>
            <input type="text" name="plate_number" placeholder="Гос.номер" required>
            <select name="company_id" required>
                <option value="">Компанияни танланг</option>
                {company_options}
            </select>
            <button type="submit">Сақлаш</button>
        </form>
    </div>

    <div class="card">
        <h3>Транспортлар рўйхати</h3>
        <table>
            <tr>
                <th>ID</th>
                <th>Марка</th>
                <th>Тип</th>
                <th>Гос.номер</th>
                <th>Компания</th>
                <th>Амал</th>
            </tr>
            {rows}
        </table>
    </div>
    """
    return render_page("Транспортлар", content)


@app.route("/vehicles/delete/<int:vehicle_id>")
def delete_vehicle(vehicle_id):
    execute_query("DELETE FROM vehicles WHERE id=%s", (vehicle_id,))
    flash("Транспорт ўчирилди.", "success")
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
            flash("Мажбурий майдонларни тўлдиринг.", "error")
            return redirect(url_for("fuel_page"))

        try:
            liters_value = float(liters)
            if liters_value <= 0:
                flash("Литр 0 дан катта бўлиши керак.", "error")
                return redirect(url_for("fuel_page"))
        except:
            flash("Литр нотўғри киритилди.", "error")
            return redirect(url_for("fuel_page"))

        speedometer_value = None
        if speedometer:
            try:
                speedometer_value = int(speedometer)
            except:
                flash("Спидометр қиймати бутун сон бўлиши керак.", "error")
                return redirect(url_for("fuel_page"))

        execute_query("""
            INSERT INTO fuel_transactions (
                vehicle_id, object_id, entry_type, liters, speedometer, entered_by, comment
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            vehicle_id, object_id, entry_type, liters_value, speedometer_value, entered_by, comment
        ))

        flash("ГСМ операцияси сақланди.", "success")
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
        <h3>ГСМ киритиш</h3>
        <form method="POST">
            <select name="object_id" required>
                <option value="">Объектни танланг</option>
                {object_options}
            </select>

            <select name="vehicle_id" required>
                <option value="">Транспортни танланг</option>
                {vehicle_options}
            </select>

            <select name="entry_type" required>
                <option value="">Турини танланг</option>
                <option value="kirim">Кирим</option>
                <option value="chiqim">Чиқим</option>
            </select>

            <input type="number" step="0.01" name="liters" placeholder="Литр" required>
            <input type="number" name="speedometer" placeholder="Спидометр">
            <input type="text" name="entered_by" placeholder="Ким киритди">
            <textarea name="comment" placeholder="Изоҳ"></textarea>
            <button type="submit">Сақлаш</button>
        </form>
    </div>
    """
    return render_page("ГСМ киритиш", content)


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
        rows += f"""
        <tr>
            <td>{t['id']}</td>
            <td>{t['object_name'] or ''}</td>
            <td>{t['company_name'] or ''}</td>
            <td>{(t['brand'] or '')} / {(t['vehicle_type'] or '')} / {(t['plate_number'] or '')}</td>
            <td>{t['entry_type']}</td>
            <td>{t['liters']}</td>
            <td>{t['speedometer'] if t['speedometer'] is not None else ''}</td>
            <td>{t['entered_by'] or ''}</td>
            <td>{t['comment'] or ''}</td>
            <td>{t['created_at']}</td>
            <td>
                <a class="small-btn" href="/transactions/delete/{t['id']}" onclick="return confirm('Ростдан ҳам ўчирмоқчимисиз?')">Ўчириш</a>
            </td>
        </tr>
        """

    content = f"""
    <div class="card">
        <h3>ГСМ журнали</h3>
        <table>
            <tr>
                <th>ID</th>
                <th>Объект</th>
                <th>Компания</th>
                <th>Транспорт</th>
                <th>Тури</th>
                <th>Литр</th>
                <th>Спидометр</th>
                <th>Киритган</th>
                <th>Изоҳ</th>
                <th>Сана</th>
                <th>Амал</th>
            </tr>
            {rows}
        </table>
    </div>
    """
    return render_page("ГСМ журнали", content)

init_db()

@app.route("/transactions/delete/<int:tx_id>")
def delete_transaction(tx_id):
    execute_query("DELETE FROM fuel_transactions WHERE id=%s", (tx_id,))
    flash("Операция ўчирилди.", "success")
    return redirect(url_for("transactions_page"))


# =========================
# START
# =========================
if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
