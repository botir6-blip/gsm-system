import os
import psycopg2
from flask import Flask, request, redirect

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_connection():
    return psycopg2.connect(DATABASE_URL, sslmode="require")


# ================= DB INIT =================

def init_tables():
    conn = get_connection()
    cur = conn.cursor()

    # Машиналар
    cur.execute("""
    CREATE TABLE IF NOT EXISTS vehicles (
        id SERIAL PRIMARY KEY,
        vehicle_name VARCHAR(100),
        plate_number VARCHAR(30),
        object_name VARCHAR(100),
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Заправка
    cur.execute("""
    CREATE TABLE IF NOT EXISTS fuel_transactions (
        id SERIAL PRIMARY KEY,
        vehicle VARCHAR(100),
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
    cur.close()
    conn.close()


init_tables()

# ================= HOME =================

@app.route("/", methods=["GET", "POST"])
def home():

    conn = get_connection()
    cur = conn.cursor()

    # машиналарни олиш
    cur.execute("""
    SELECT vehicle_name FROM vehicles
    WHERE is_active = TRUE
    ORDER BY vehicle_name
    """)
    vehicles = cur.fetchall()

    if request.method == "POST":
        vehicle = request.form.get("vehicle")
        object_name = request.form.get("object")
        entry_type = request.form.get("entry_type")
        liters = request.form.get("liters")
        odometer = request.form.get("odometer")
        entered_by = request.form.get("entered_by")

        driver_confirmed = False
        if entry_type == "external":
            driver_confirmed = True

        cur.execute("""
        INSERT INTO fuel_transactions
        (vehicle, object_name, entry_type, liters, odometer, entered_by, driver_confirmed)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (vehicle, object_name, entry_type, liters, odometer, entered_by, driver_confirmed))

        conn.commit()
        return redirect("/")

    # журнал
    cur.execute("""
    SELECT id, vehicle, object_name, entry_type, liters, odometer,
           entered_by, driver_confirmed, dispatcher_status, comment
    FROM fuel_transactions
    ORDER BY id DESC
    """)

    rows = cur.fetchall()

    cur.close()
    conn.close()

    html = """
    <html>
    <head>
    <meta charset="UTF-8">
    <style>
    body {font-family: Arial; padding:20px; background:#f7f7f7;}
    table {width:100%; border-collapse:collapse; background:white;}
    th,td {border:1px solid #ccc; padding:8px;}
    th {background:#eee;}
    .ok {color:green;}
    .bad {color:red;}
    .new {background:#fff3cd;}
    .approved {background:#d4edda;}
    .rejected {background:#f8d7da;}
    </style>
    </head>
    <body>

    <h2>Заправка киритиш</h2>

    <form method="post">

    Машина:<br>
    <select name="vehicle" required>
    <option value="">Танланг</option>
    """

    for v in vehicles:
        html += f"<option value='{v[0]}'>{v[0]}</option>"

    html += """
    </select><br><br>

    Объект:<br>
    <input name="object"><br><br>

    Тури:<br>
    <select name="entry_type">
        <option value="internal">Ички</option>
        <option value="external">Ташқи</option>
    </select><br><br>

    Литр:<br>
    <input name="liters"><br><br>

    Одометр:<br>
    <input name="odometer"><br><br>

    Ким киритди:<br>
    <input name="entered_by"><br><br>

    <button>Сақлаш</button>
    </form>

    <br>
    <a href="/vehicles">🚗 Машиналарни бошқариш</a>

    <h2>Журнал</h2>

    <table>
    <tr>
    <th>ID</th><th>Машина</th><th>Объект</th><th>Тури</th>
    <th>Литр</th><th>Одометр</th><th>Киритган</th>
    <th>Ҳайдовчи</th><th>Статус</th><th>Изоҳ</th><th>Амал</th>
    </tr>
    """

    for r in rows:

        status = "new"
        if r[8] == "approved":
            status = "approved"
        elif r[8] == "rejected":
            status = "rejected"

        actions = ""

        if r[3] == "internal" and not r[7] and r[8] == "new":
            actions += f"""
            <form method='post' action='/driver/{r[0]}' style='display:inline'>
            <button>Driver OK</button></form>
            """

        if r[8] == "new" and r[7]:
            actions += f"""
            <form method='post' action='/approve/{r[0]}' style='display:inline'>
            <button>АТС OK</button></form>

            <form method='post' action='/reject/{r[0]}' style='display:inline'>
            <input name='comment' placeholder='Сабаб'>
            <button>❌</button></form>
            """

        html += f"""
        <tr class="{status}">
        <td>{r[0]}</td>
        <td>{r[1]}</td>
        <td>{r[2]}</td>
        <td>{r[3]}</td>
        <td>{r[4]}</td>
        <td>{r[5]}</td>
        <td>{r[6]}</td>
        <td>{'✅' if r[7] else '❌'}</td>
        <td>{r[8]}</td>
        <td>{r[9] or ''}</td>
        <td>{actions}</td>
        </tr>
        """

    html += "</table></body></html>"

    return html


# ================= VEHICLES =================

@app.route("/vehicles", methods=["GET", "POST"])
def vehicles():

    conn = get_connection()
    cur = conn.cursor()

    if request.method == "POST":
        name = request.form.get("name")
        plate = request.form.get("plate")
        obj = request.form.get("object")

        cur.execute("""
        INSERT INTO vehicles (vehicle_name, plate_number, object_name)
        VALUES (%s,%s,%s)
        """, (name, plate, obj))

        conn.commit()
        return redirect("/vehicles")

    cur.execute("SELECT * FROM vehicles ORDER BY id DESC")
    rows = cur.fetchall()

    cur.close()
    conn.close()

    html = """
    <h2>Машина қўшиш</h2>
    <form method="post">
    Номи:<br><input name="name"><br>
    Рақами:<br><input name="plate"><br>
    Объект:<br><input name="object"><br>
    <button>Сақлаш</button>
    </form>

    <br><a href="/">← Орқага</a>

    <h2>Рўйхат</h2>
    <table border=1>
    <tr><th>ID</th><th>Номи</th><th>Рақами</th><th>Объект</th></tr>
    """

    for r in rows:
        html += f"<tr><td>{r[0]}</td><td>{r[1]}</td><td>{r[2]}</td><td>{r[3]}</td></tr>"

    html += "</table>"
    return html


# ================= ACTIONS =================

@app.route("/driver/<int:id>", methods=["POST"])
def driver(id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE fuel_transactions SET driver_confirmed=TRUE WHERE id=%s", (id,))
    conn.commit()
    return redirect("/")


@app.route("/approve/<int:id>", methods=["POST"])
def approve(id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE fuel_transactions SET dispatcher_status='approved', comment=NULL WHERE id=%s", (id,))
    conn.commit()
    return redirect("/")


@app.route("/reject/<int:id>", methods=["POST"])
def reject(id):
    comment = request.form.get("comment")
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE fuel_transactions SET dispatcher_status='rejected', comment=%s WHERE id=%s", (comment, id))
    conn.commit()
    return redirect("/")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
