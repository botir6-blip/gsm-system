import os
import psycopg2
from flask import Flask, request, redirect

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_connection():
    return psycopg2.connect(DATABASE_URL)


def init_db():
    conn = get_connection()
    cur = conn.cursor()

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
    cur.close()
    conn.close()


def ensure_entry_type_column():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name='fuel_transactions' AND column_name='entry_type';
    """)
    exists = cur.fetchone()

    if not exists:
        cur.execute("""
            ALTER TABLE fuel_transactions
            ADD COLUMN entry_type VARCHAR(20) DEFAULT 'internal';
        """)
        conn.commit()
        print("✅ entry_type устуни қўшилди")
    else:
        print("✅ entry_type устуни аллақачон бор")

    cur.close()
    conn.close()


init_db()
ensure_entry_type_column()


@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        vehicle = request.form.get("vehicle", "").strip()
        object_name = request.form.get("object", "").strip()
        entry_type = request.form.get("entry_type", "internal").strip()
        liters = request.form.get("liters", "").strip()
        odometer = request.form.get("odometer", "").strip()
        entered_by = request.form.get("entered_by", "").strip()

        if not vehicle or not object_name or not liters or not odometer or not entered_by:
            return "❌ Барча майдонларни тўлдиринг"

        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
        INSERT INTO fuel_transactions
        (vehicle, object_name, entry_type, liters, odometer, entered_by)
        VALUES (%s, %s, %s, %s, %s, %s)
        """, (vehicle, object_name, entry_type, liters, odometer, entered_by))

        conn.commit()
        cur.close()
        conn.close()

        return redirect("/")

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    SELECT id, vehicle, object_name, entry_type, liters, odometer,
           entered_by, driver_confirmed, dispatcher_status
    FROM fuel_transactions
    ORDER BY id DESC
    """)

    rows = cur.fetchall()

    cur.close()
    conn.close()

    html = """
    <h2>Заправка киритиш</h2>

    <form method="post">

    Машина:<br>
    <input name="vehicle" required><br><br>

    Объект:<br>
    <input name="object" required><br><br>

    Тури:<br>
    <select name="entry_type">
        <option value="internal">Ички объект</option>
        <option value="external">Ташқи объект</option>
    </select><br><br>

    Литр:<br>
    <input name="liters" type="number" step="0.01" required><br><br>

    Одометр:<br>
    <input name="odometer" type="number" required><br><br>

    Ким киритди:<br>
    <input name="entered_by" required><br><br>

    <button type="submit">Сақлаш</button>

    </form>

    <h2>Журнал</h2>

    <table border="1" cellpadding="8">
    <tr>
    <th>ID</th>
    <th>Машина</th>
    <th>Объект</th>
    <th>Тури</th>
    <th>Литр</th>
    <th>Одометр</th>
    <th>Киритган</th>
    <th>Driver OK</th>
    <th>АТС статус</th>
    <th>Амал</th>
    </tr>
    """

    for r in rows:
        actions = ""

        if not r[7]:
            actions += f"""
            <form method='post' action='/driver_confirm/{r[0]}' style='display:inline'>
                <button type='submit'>Driver OK</button>
            </form>
            """

        if r[8] == "new":
            actions += f"""
            <form method='post' action='/approve/{r[0]}' style='display:inline'>
                <button type='submit'>АТС тасдиқ</button>
            </form>
            """

        html += f"""
        <tr>
        <td>{r[0]}</td>
        <td>{r[1]}</td>
        <td>{r[2]}</td>
        <td>{r[3]}</td>
        <td>{r[4]}</td>
        <td>{r[5]}</td>
        <td>{r[6]}</td>
        <td>{'✅' if r[7] else '❌'}</td>
        <td>{r[8]}</td>
        <td>{actions}</td>
        </tr>
        """

    html += "</table>"

    return html


@app.route("/driver_confirm/<int:id>", methods=["POST"])
def driver_confirm(id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    UPDATE fuel_transactions
    SET driver_confirmed = TRUE
    WHERE id = %s
    """, (id,))

    conn.commit()
    cur.close()
    conn.close()

    return redirect("/")


@app.route("/approve/<int:id>", methods=["POST"])
def approve(id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    UPDATE fuel_transactions
    SET dispatcher_status = 'approved'
    WHERE id = %s
    """, (id,))

    conn.commit()
    cur.close()
    conn.close()

    return redirect("/")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
