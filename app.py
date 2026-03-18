import os
import psycopg2
from flask import Flask, request, redirect

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_connection():
    if not DATABASE_URL:
        raise Exception("DATABASE_URL topilmadi")
    return psycopg2.connect(DATABASE_URL, sslmode="require")


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS fuel_transactions (
        id SERIAL PRIMARY KEY,
        vehicle VARCHAR(50),
        object_name VARCHAR(100),
        liters NUMERIC,
        odometer INTEGER,
        entered_by VARCHAR(100),
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
        SELECT 1
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

    cur.close()
    conn.close()


def ensure_driver_confirmed_column():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT 1
        FROM information_schema.columns
        WHERE table_name='fuel_transactions' AND column_name='driver_confirmed';
    """)
    exists = cur.fetchone()

    if not exists:
        cur.execute("""
            ALTER TABLE fuel_transactions
            ADD COLUMN driver_confirmed BOOLEAN DEFAULT FALSE;
        """)
        conn.commit()

    cur.close()
    conn.close()


def ensure_dispatcher_status_column():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT 1
        FROM information_schema.columns
        WHERE table_name='fuel_transactions' AND column_name='dispatcher_status';
    """)
    exists = cur.fetchone()

    if not exists:
        cur.execute("""
            ALTER TABLE fuel_transactions
            ADD COLUMN dispatcher_status VARCHAR(20) DEFAULT 'new';
        """)
        conn.commit()

    cur.close()
    conn.close()


def ensure_comment_column():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT 1
        FROM information_schema.columns
        WHERE table_name='fuel_transactions' AND column_name='comment';
    """)
    exists = cur.fetchone()

    if not exists:
        cur.execute("""
            ALTER TABLE fuel_transactions
            ADD COLUMN comment TEXT;
        """)
        conn.commit()

    cur.close()
    conn.close()


init_db()
ensure_entry_type_column()
ensure_driver_confirmed_column()
ensure_dispatcher_status_column()
ensure_comment_column()


@app.route("/", methods=["GET", "POST"])
def home():
    try:
        if request.method == "POST":
            vehicle = request.form.get("vehicle", "").strip()
            object_name = request.form.get("object", "").strip()
            entry_type = request.form.get("entry_type", "internal").strip()
            liters = request.form.get("liters", "").strip()
            odometer = request.form.get("odometer", "").strip()
            entered_by = request.form.get("entered_by", "").strip()

            if not vehicle or not object_name or not liters or not odometer or not entered_by:
                return "❌ Барча майдонларни тўлдиринг"

            driver_confirmed = False
            if entry_type == "external":
                driver_confirmed = True

            conn = get_connection()
            cur = conn.cursor()

            cur.execute("""
            INSERT INTO fuel_transactions
            (vehicle, object_name, entry_type, liters, odometer, entered_by, driver_confirmed)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (vehicle, object_name, entry_type, liters, odometer, entered_by, driver_confirmed))

            conn.commit()
            cur.close()
            conn.close()

            return redirect("/")

        conn = get_connection()
        cur = conn.cursor()

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
            <title>Заправка журнали</title>
            <style>
                body { font-family: Arial, sans-serif; padding: 20px; background: #f7f7f7; }
                table { border-collapse: collapse; width: 100%; background: white; }
                th, td { border: 1px solid #ccc; padding: 8px; text-align: left; vertical-align: top; }
                th { background: #eee; }
                input, select, textarea, button { padding: 8px; margin: 4px 0 10px; width: 300px; max-width: 100%; }
                .status-new { background: #fff3cd; font-weight: bold; }
                .status-approved { background: #d4edda; font-weight: bold; }
                .status-rejected { background: #f8d7da; font-weight: bold; }
                .btn-inline { display: inline-block; width: auto; margin-right: 5px; margin-bottom: 5px; }
                .small-textarea { width: 220px; height: 60px; }
                .section { background: white; padding: 15px; margin-bottom: 20px; border: 1px solid #ddd; }
            </style>
        </head>
        <body>

        <div class="section">
            <h2>Заправка киритиш</h2>
            <form method="post">
                Машина:<br>
                <input name="vehicle" required><br>

                Объект:<br>
                <input name="object" required><br>

                Тури:<br>
                <select name="entry_type">
                    <option value="internal">Ички объект</option>
                    <option value="external">Ташқи объект</option>
                </select><br>

                Литр:<br>
                <input name="liters" type="number" step="0.01" required><br>

                Одометр:<br>
                <input name="odometer" type="number" required><br>

                Ким киритди:<br>
                <input name="entered_by" required><br>

                <button type="submit">Сақлаш</button>
            </form>
        </div>

        <div class="section">
            <h2>Журнал</h2>
            <table>
                <tr>
                    <th>ID</th>
                    <th>Машина</th>
                    <th>Объект</th>
                    <th>Тури</th>
                    <th>Литр</th>
                    <th>Одометр</th>
                    <th>Киритган</th>
                    <th>Ҳайдовчи</th>
                    <th>АТС статус</th>
                    <th>Изоҳ</th>
                    <th>Амал</th>
                </tr>
        """

        for r in rows:
            row_id = r[0]
            vehicle = r[1]
            object_name = r[2]
            entry_type = r[3]
            liters = r[4]
            odometer = r[5]
            entered_by = r[6]
            driver_confirmed = r[7]
            dispatcher_status = r[8]
            comment = r[9] or ""

            actions = ""

            if entry_type == "internal" and not driver_confirmed and dispatcher_status == "new":
                actions += f"""
                <form method='post' action='/driver_confirm/{row_id}' style='display:inline;'>
                    <button class='btn-inline' type='submit'>Ҳайдовчи тасдиғи</button>
                </form>
                """

            if dispatcher_status == "new" and driver_confirmed:
                actions += f"""
                <form method='post' action='/approve/{row_id}' style='display:inline;'>
                    <button class='btn-inline' type='submit'>АТС тасдиқ</button>
                </form>

                <form method='post' action='/reject/{row_id}' style='display:inline; margin-top:5px;'>
                    <textarea class='small-textarea' name='comment' placeholder='Рад этиш сабаби'></textarea><br>
                    <button class='btn-inline' type='submit'>Рад этиш</button>
                </form>
                """

            if dispatcher_status == "approved":
                status_class = "status-approved"
                status_text = "✅ Тасдиқланган"
            elif dispatcher_status == "rejected":
                status_class = "status-rejected"
                status_text = "❌ Рад этилган"
            else:
                status_class = "status-new"
                status_text = "⏳ Янги"

            html += f"""
            <tr>
                <td>{row_id}</td>
                <td>{vehicle}</td>
                <td>{object_name}</td>
                <td>{'Ички' if entry_type == 'internal' else 'Ташқи'}</td>
                <td>{liters}</td>
                <td>{odometer}</td>
                <td>{entered_by}</td>
                <td>{'✅' if driver_confirmed else '❌'}</td>
                <td class="{status_class}">{status_text}</td>
                <td>{comment}</td>
                <td>{actions}</td>
            </tr>
            """

        html += """
            </table>
        </div>

        </body>
        </html>
        """

        return html

    except Exception as e:
        return f"XATO: {str(e)}"


@app.route("/driver_confirm/<int:id>", methods=["POST"])
def driver_confirm(id):
    try:
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
    except Exception as e:
        return f"XATO: {str(e)}"


@app.route("/approve/<int:id>", methods=["POST"])
def approve(id):
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
        UPDATE fuel_transactions
        SET dispatcher_status = 'approved',
            comment = NULL
        WHERE id = %s
        """, (id,))

        conn.commit()
        cur.close()
        conn.close()

        return redirect("/")
    except Exception as e:
        return f"XATO: {str(e)}"


@app.route("/reject/<int:id>", methods=["POST"])
def reject(id):
    try:
        comment = request.form.get("comment", "").strip()

        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
        UPDATE fuel_transactions
        SET dispatcher_status = 'rejected',
            comment = %s
        WHERE id = %s
        """, (comment, id))

        conn.commit()
        cur.close()
        conn.close()

        return redirect("/")
    except Exception as e:
        return f"XATO: {str(e)}"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
