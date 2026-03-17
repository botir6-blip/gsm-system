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
            vehicle VARCHAR(50) NOT NULL,
            object_name VARCHAR(100) NOT NULL,
            liters NUMERIC(10,2) NOT NULL,
            odometer INTEGER,
            entered_by VARCHAR(100),
            status VARCHAR(20) DEFAULT 'new',
            comment TEXT,
            checked_by VARCHAR(100),
            checked_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    cur.close()
    conn.close()


@app.route("/", methods=["GET", "POST"])
def home():
    init_db()

    if request.method == "POST":
        vehicle = request.form["vehicle"]
        object_name = request.form["object"]
        liters = request.form["liters"]
        odometer = request.form["odometer"]
        entered_by = request.form["entered_by"]
        comment = request.form.get("comment", "")

        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO fuel_transactions
            (vehicle, object_name, liters, odometer, entered_by, comment, status)
            VALUES (%s, %s, %s, %s, %s, %s, 'new')
        """, (vehicle, object_name, liters, odometer, entered_by, comment))

        conn.commit()
        cur.close()
        conn.close()

        return redirect("/")

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, vehicle, object_name, liters, odometer, entered_by,
               status, comment, checked_by, checked_at, created_at
        FROM fuel_transactions
        ORDER BY id DESC
    """)
    transactions = cur.fetchall()

    cur.close()
    conn.close()

    html = """
    <html>
    <head>
        <meta charset="utf-8">
        <title>ГСМ назорати</title>
    </head>
    <body style="font-family: Arial; padding: 20px;">
        <h2>ГСМ заправка киритиш</h2>

        <form method="post" style="margin-bottom: 30px;">
            <label>Машина:</label><br>
            <input name="vehicle" required><br><br>

            <label>Объект:</label><br>
            <input name="object" required><br><br>

            <label>Литр:</label><br>
            <input name="liters" type="number" step="0.01" required><br><br>

            <label>Одометр:</label><br>
            <input name="odometer" type="number"><br><br>

            <label>Ким киритди:</label><br>
            <input name="entered_by" required><br><br>

            <label>Изоҳ:</label><br>
            <textarea name="comment" rows="3" cols="40"></textarea><br><br>

            <button type="submit">Сақлаш</button>
        </form>

        <h2>Заправка журнали</h2>

        <table border="1" cellpadding="8" cellspacing="0">
            <tr>
                <th>ID</th>
                <th>Машина</th>
                <th>Объект</th>
                <th>Литр</th>
                <th>Одометр</th>
                <th>Киритган</th>
                <th>Статус</th>
                <th>Изоҳ</th>
                <th>Текширган</th>
                <th>Текширилган вақт</th>
                <th>Сана</th>
                <th>Амал</th>
            </tr>
    """

    for t in transactions:
        tx_id = t[0]
        vehicle = t[1]
        object_name = t[2]
        liters = t[3]
        odometer = t[4] if t[4] is not None else ""
        entered_by = t[5] if t[5] else ""
        status = t[6] if t[6] else ""
        comment = t[7] if t[7] else ""
        checked_by = t[8] if t[8] else ""
        checked_at = t[9] if t[9] else ""
        created_at = t[10] if t[10] else ""

        actions = ""
        if status == "new":
            actions = f"""
                <form method="post" action="/approve/{tx_id}" style="display:inline;">
                    <input name="checked_by" placeholder="Диспетчер" required>
                    <button type="submit">Тасдиқлаш</button>
                </form>

                <form method="post" action="/reject/{tx_id}" style="display:inline; margin-left:5px;">
                    <input name="checked_by" placeholder="Диспетчер" required>
                    <input name="comment" placeholder="Сабаб" required>
                    <button type="submit">Рад этиш</button>
                </form>
            """
        else:
            actions = "-"

        html += f"""
            <tr>
                <td>{tx_id}</td>
                <td>{vehicle}</td>
                <td>{object_name}</td>
                <td>{liters}</td>
                <td>{odometer}</td>
                <td>{entered_by}</td>
                <td>{status}</td>
                <td>{comment}</td>
                <td>{checked_by}</td>
                <td>{checked_at}</td>
                <td>{created_at}</td>
                <td>{actions}</td>
            </tr>
        """

    html += """
        </table>
    </body>
    </html>
    """

    return html


@app.route("/approve/<int:tx_id>", methods=["POST"])
def approve(tx_id):
    checked_by = request.form["checked_by"]

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE fuel_transactions
        SET status = 'approved',
            checked_by = %s,
            checked_at = CURRENT_TIMESTAMP
        WHERE id = %s
    """, (checked_by, tx_id))

    conn.commit()
    cur.close()
    conn.close()

    return redirect("/")


@app.route("/reject/<int:tx_id>", methods=["POST"])
def reject(tx_id):
    checked_by = request.form["checked_by"]
    comment = request.form["comment"]

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE fuel_transactions
        SET status = 'rejected',
            checked_by = %s,
            checked_at = CURRENT_TIMESTAMP,
            comment = %s
        WHERE id = %s
    """, (checked_by, comment, tx_id))

    conn.commit()
    cur.close()
    conn.close()

    return redirect("/")
