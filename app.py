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

    # Заправка операциялари
    cur.execute("""
    CREATE TABLE IF NOT EXISTS fuel_transactions (
        id SERIAL PRIMARY KEY,
        vehicle VARCHAR(100),
        object_name VARCHAR(100),
        entry_type VARCHAR(20), -- internal / external
        liters NUMERIC,
        odometer INTEGER,
        entered_by VARCHAR(100),

        manager_status VARCHAR(20) DEFAULT 'new',     -- new / approved / rejected
        fueled BOOLEAN DEFAULT FALSE,                 -- ёқилғи берилдими
        driver_confirmed BOOLEAN DEFAULT FALSE,       -- ҳайдовчи тасдиқладими
        dispatcher_status VARCHAR(20) DEFAULT 'new',  -- new / approved / rejected
        closed BOOLEAN DEFAULT FALSE,                 -- операция ёпилдими

        comment TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    cur.close()
    conn.close()


def ensure_column(table_name, column_name, column_type_sql):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name=%s AND column_name=%s
    """, (table_name, column_name))

    exists = cur.fetchone()

    if not exists:
        cur.execute(f"""
            ALTER TABLE {table_name}
            ADD COLUMN {column_name} {column_type_sql}
        """)
        conn.commit()

    cur.close()
    conn.close()


def ensure_schema():
    # Эски база бўлса ҳам, керакли устунларни қўшиб чиқади
    ensure_column("fuel_transactions", "manager_status", "VARCHAR(20) DEFAULT 'new'")
    ensure_column("fuel_transactions", "fueled", "BOOLEAN DEFAULT FALSE")
    ensure_column("fuel_transactions", "driver_confirmed", "BOOLEAN DEFAULT FALSE")
    ensure_column("fuel_transactions", "dispatcher_status", "VARCHAR(20) DEFAULT 'new'")
    ensure_column("fuel_transactions", "closed", "BOOLEAN DEFAULT FALSE")
    ensure_column("fuel_transactions", "comment", "TEXT")


init_tables()
ensure_schema()


# ================= HELPERS =================

def get_stage_text(row):
    """
    row:
    0 id
    1 vehicle
    2 object_name
    3 entry_type
    4 liters
    5 odometer
    6 entered_by
    7 manager_status
    8 fueled
    9 driver_confirmed
    10 dispatcher_status
    11 closed
    12 comment
    """

    entry_type = row[3]
    manager_status = row[7]
    fueled = row[8]
    driver_confirmed = row[9]
    dispatcher_status = row[10]
    closed = row[11]

    if entry_type == "external":
        if dispatcher_status == "rejected":
            return "Отклонено АТС"
        if closed:
            return "Закрыто"
        return "Ожидает проверки АТС"

    # internal
    if manager_status == "rejected":
        return "Отклонено руководителем"
    if dispatcher_status == "rejected":
        return "Отклонено АТС"
    if closed:
        return "Закрыто"
    if manager_status == "new":
        return "Ожидает согласования"
    if manager_status == "approved" and not fueled:
        return "Ожидает выдачи топлива"
    if fueled and not driver_confirmed:
        return "Ожидает подтверждения водителя"
    if fueled and driver_confirmed and not closed:
        return "Ожидает проверки АТС"

    return "В процессе"


def get_row_class(row):
    manager_status = row[7]
    dispatcher_status = row[10]
    closed = row[11]

    if manager_status == "rejected" or dispatcher_status == "rejected":
        return "rejected"
    if closed:
        return "approved"
    return "new"


def safe(val):
    return "" if val is None else str(val)


# ================= HOME =================

@app.route("/", methods=["GET", "POST"])
def home():
    conn = get_connection()
    cur = conn.cursor()

    # Машиналар рўйхати
    cur.execute("""
    SELECT vehicle_name
    FROM vehicles
    WHERE is_active = TRUE
    ORDER BY vehicle_name
    """)
    vehicles = cur.fetchall()

    if request.method == "POST":
        vehicle = request.form.get("vehicle", "").strip()
        object_name = request.form.get("object", "").strip()
        entry_type = request.form.get("entry_type", "").strip()
        liters = request.form.get("liters", "").strip()
        odometer = request.form.get("odometer", "").strip()
        entered_by = request.form.get("entered_by", "").strip()

        if not vehicle or not entry_type or not liters or not entered_by:
            cur.close()
            conn.close()
            return redirect("/")

        try:
            liters_value = float(liters)
        except:
            liters_value = 0

        odometer_value = None
        if odometer:
            try:
                odometer_value = int(odometer)
            except:
                odometer_value = None

        # Ташқи объект учун қисқартирилган схема:
        # ҳайдовчи ўзи киритади -> олинган деб ҳисобланади -> АТС текширади
        if entry_type == "external":
            manager_status = "approved"
            fueled = True
            driver_confirmed = True
        else:
            manager_status = "new"
            fueled = False
            driver_confirmed = False

        cur.execute("""
        INSERT INTO fuel_transactions
        (
            vehicle, object_name, entry_type, liters, odometer, entered_by,
            manager_status, fueled, driver_confirmed, dispatcher_status, closed, comment
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'new', FALSE, NULL)
        """, (
            vehicle, object_name, entry_type, liters_value, odometer_value, entered_by,
            manager_status, fueled, driver_confirmed
        ))

        conn.commit()
        cur.close()
        conn.close()
        return redirect("/")

    # Журнал
    cur.execute("""
    SELECT id, vehicle, object_name, entry_type, liters, odometer,
           entered_by, manager_status, fueled, driver_confirmed,
           dispatcher_status, closed, comment
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
        <title>Учет ГСМ</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                padding: 20px;
                background: #f5f7fa;
                color: #222;
            }
            h1, h2 {
                margin-bottom: 10px;
            }
            .card {
                background: white;
                padding: 16px;
                border-radius: 10px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
                margin-bottom: 20px;
            }
            table {
                width: 100%;
                border-collapse: collapse;
                background: white;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            }
            th, td {
                border: 1px solid #ddd;
                padding: 8px;
                vertical-align: top;
                text-align: left;
                font-size: 14px;
            }
            th {
                background: #eef2f7;
            }
            input, select, button {
                padding: 8px;
                margin-top: 4px;
                margin-bottom: 10px;
                width: 100%;
                max-width: 320px;
                box-sizing: border-box;
            }
            button {
                cursor: pointer;
                width: auto;
                padding: 8px 12px;
                margin-right: 6px;
                margin-bottom: 6px;
            }
            .new {
                background: #fff8db;
            }
            .approved {
                background: #e9f9ee;
            }
            .rejected {
                background: #fdeaea;
            }
            .badge {
                display: inline-block;
                padding: 4px 8px;
                border-radius: 6px;
                font-size: 12px;
                font-weight: bold;
                background: #e9ecef;
            }
            .actions form {
                display: inline-block;
                margin: 0 4px 4px 0;
            }
            .small-input {
                width: 140px;
                margin-right: 6px;
            }
            a {
                text-decoration: none;
                color: #0d6efd;
            }
        </style>
    </head>
    <body>

    <h1>Система учета ГСМ</h1>

    <div class="card">
        <h2>Новая запись</h2>
        <form method="post">

            Транспорт:<br>
            <select name="vehicle" required>
                <option value="">Выберите транспорт</option>
    """

    for v in vehicles:
        html += f"<option value='{safe(v[0])}'>{safe(v[0])}</option>"

    html += """
            </select><br>

            Объект:<br>
            <input name="object" placeholder="Введите объект"><br>

            Тип операции:<br>
            <select name="entry_type" required>
                <option value="internal">Внутренний объект</option>
                <option value="external">Внешний объект</option>
            </select><br>

            Объем топлива (л):<br>
            <input name="liters" type="number" step="0.01" placeholder="Например: 120"><br>

            Одометр:<br>
            <input name="odometer" type="number" placeholder="Например: 152340"><br>

            Кто внес запись:<br>
            <input name="entered_by" placeholder="ФИО"><br>

            <button type="submit">Сохранить</button>
        </form>

        <a href="/vehicles">🚗 Управление транспортом</a>
    </div>

    <div class="card">
        <h2>Журнал операций</h2>
        <table>
            <tr>
                <th>ID</th>
                <th>Транспорт</th>
                <th>Объект</th>
                <th>Тип</th>
                <th>Литры</th>
                <th>Одометр</th>
                <th>Кто внес</th>
                <th>Согласование</th>
                <th>Выдача</th>
                <th>Водитель</th>
                <th>АТС</th>
                <th>Этап</th>
                <th>Комментарий</th>
                <th>Действия</th>
            </tr>
    """

    for r in rows:
        row_class = get_row_class(r)
        stage_text = get_stage_text(r)

        manager_status = r[7]
        fueled = r[8]
        driver_confirmed = r[9]
        dispatcher_status = r[10]
        closed = r[11]
        entry_type = r[3]
        item_id = r[0]

        manager_text = "✅ Подтверждено" if manager_status == "approved" else (
            "❌ Отклонено" if manager_status == "rejected" else "⏳ Ожидает"
        )
        fueled_text = "✅ Выдано" if fueled else "❌ Нет"
        driver_text = "✅ Подтвердил" if driver_confirmed else "❌ Нет"
        ats_text = "✅ Закрыто" if closed else (
            "❌ Отклонено" if dispatcher_status == "rejected" else "⏳ Ожидает"
        )

        actions = "<div class='actions'>"

        # ===== Внутренний объект =====
        if entry_type == "internal":
            # 1. Руководитель подтверждает / отклоняет
            if manager_status == "new":
                actions += f"""
                <form method='post' action='/manager_approve/{item_id}'>
                    <button>Подтвердить заявку</button>
                </form>

                <form method='post' action='/manager_reject/{item_id}'>
                    <input class='small-input' name='comment' placeholder='Причина отказа' required>
                    <button>Отклонить</button>
                </form>
                """

            # 2. После подтверждения руководителем - выдача топлива
            if manager_status == "approved" and not fueled:
                actions += f"""
                <form method='post' action='/fuel/{item_id}'>
                    <button>Выдать топливо</button>
                </form>
                """

            # 3. После выдачи топлива - подтверждение водителя
            if manager_status == "approved" and fueled and not driver_confirmed:
                actions += f"""
                <form method='post' action='/driver/{item_id}'>
                    <button>Подтвердить получение</button>
                </form>
                """

            # 4. После водителя - закрытие АТС
            if manager_status == "approved" and fueled and driver_confirmed and not closed and dispatcher_status == "new":
                actions += f"""
                <form method='post' action='/close/{item_id}'>
                    <button>Закрыть операцию</button>
                </form>

                <form method='post' action='/dispatcher_reject/{item_id}'>
                    <input class='small-input' name='comment' placeholder='Причина отказа АТС' required>
                    <button>Отклонить АТС</button>
                </form>
                """

        # ===== Ташқи объект =====
        if entry_type == "external":
            # External: киритилгандаёқ fueled=True, driver_confirmed=True
            if not closed and dispatcher_status == "new":
                actions += f"""
                <form method='post' action='/close/{item_id}'>
                    <button>Закрыть операцию</button>
                </form>

                <form method='post' action='/dispatcher_reject/{item_id}'>
                    <input class='small-input' name='comment' placeholder='Причина отказа АТС' required>
                    <button>Отклонить АТС</button>
                </form>
                """

        actions += "</div>"

        html += f"""
        <tr class="{row_class}">
            <td>{safe(r[0])}</td>
            <td>{safe(r[1])}</td>
            <td>{safe(r[2])}</td>
            <td>{'Внутренний' if entry_type == 'internal' else 'Внешний'}</td>
            <td>{safe(r[4])}</td>
            <td>{safe(r[5])}</td>
            <td>{safe(r[6])}</td>
            <td>{manager_text}</td>
            <td>{fueled_text}</td>
            <td>{driver_text}</td>
            <td>{ats_text}</td>
            <td><span class="badge">{stage_text}</span></td>
            <td>{safe(r[12])}</td>
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


# ================= VEHICLES =================

@app.route("/vehicles", methods=["GET", "POST"])
def vehicles():
    conn = get_connection()
    cur = conn.cursor()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        plate = request.form.get("plate", "").strip()
        obj = request.form.get("object", "").strip()

        if name:
            cur.execute("""
            INSERT INTO vehicles (vehicle_name, plate_number, object_name)
            VALUES (%s, %s, %s)
            """, (name, plate, obj))
            conn.commit()

        cur.close()
        conn.close()
        return redirect("/vehicles")

    cur.execute("""
    SELECT id, vehicle_name, plate_number, object_name, is_active
    FROM vehicles
    ORDER BY id DESC
    """)
    rows = cur.fetchall()

    cur.close()
    conn.close()

    html = """
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Транспорт</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                padding: 20px;
                background: #f5f7fa;
            }
            .card {
                background: white;
                padding: 16px;
                border-radius: 10px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
                margin-bottom: 20px;
            }
            table {
                width: 100%;
                border-collapse: collapse;
                background: white;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            }
            th, td {
                border: 1px solid #ddd;
                padding: 8px;
                text-align: left;
            }
            th {
                background: #eef2f7;
            }
            input, button {
                padding: 8px;
                margin-top: 4px;
                margin-bottom: 10px;
                width: 100%;
                max-width: 320px;
                box-sizing: border-box;
            }
            button {
                width: auto;
                cursor: pointer;
            }
            a {
                text-decoration: none;
                color: #0d6efd;
            }
        </style>
    </head>
    <body>

    <div class="card">
        <h2>Добавить транспорт</h2>
        <form method="post">
            Наименование:<br>
            <input name="name" placeholder="Например: КамАЗ 6520"><br>

            Госномер:<br>
            <input name="plate" placeholder="Например: 01 A 123 BC"><br>

            Объект:<br>
            <input name="object" placeholder="Например: Буровая 12"><br>

            <button type="submit">Сохранить</button>
        </form>

        <a href="/">← Назад</a>
    </div>

    <div class="card">
        <h2>Список транспорта</h2>
        <table>
            <tr>
                <th>ID</th>
                <th>Наименование</th>
                <th>Госномер</th>
                <th>Объект</th>
                <th>Активен</th>
            </tr>
    """

    for r in rows:
        html += f"""
        <tr>
            <td>{safe(r[0])}</td>
            <td>{safe(r[1])}</td>
            <td>{safe(r[2])}</td>
            <td>{safe(r[3])}</td>
            <td>{"Да" if r[4] else "Нет"}</td>
        </tr>
        """

    html += """
        </table>
    </div>

    </body>
    </html>
    """

    return html


# ================= ACTIONS =================

@app.route("/manager_approve/<int:item_id>", methods=["POST"])
def manager_approve(item_id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    UPDATE fuel_transactions
    SET manager_status='approved',
        comment=NULL
    WHERE id=%s
    """, (item_id,))

    conn.commit()
    cur.close()
    conn.close()
    return redirect("/")


@app.route("/manager_reject/<int:item_id>", methods=["POST"])
def manager_reject(item_id):
    comment = request.form.get("comment", "").strip()

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    UPDATE fuel_transactions
    SET manager_status='rejected',
        comment=%s
    WHERE id=%s
    """, (comment, item_id))

    conn.commit()
    cur.close()
    conn.close()
    return redirect("/")


@app.route("/fuel/<int:item_id>", methods=["POST"])
def fuel(item_id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    UPDATE fuel_transactions
    SET fueled=TRUE,
        comment=NULL
    WHERE id=%s
      AND manager_status='approved'
    """, (item_id,))

    conn.commit()
    cur.close()
    conn.close()
    return redirect("/")


@app.route("/driver/<int:item_id>", methods=["POST"])
def driver(item_id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    UPDATE fuel_transactions
    SET driver_confirmed=TRUE,
        comment=NULL
    WHERE id=%s
      AND fueled=TRUE
    """, (item_id,))

    conn.commit()
    cur.close()
    conn.close()
    return redirect("/")


@app.route("/close/<int:item_id>", methods=["POST"])
def close_operation(item_id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    UPDATE fuel_transactions
    SET closed=TRUE,
        dispatcher_status='approved',
        comment=NULL
    WHERE id=%s
    """, (item_id,))

    conn.commit()
    cur.close()
    conn.close()
    return redirect("/")


@app.route("/dispatcher_reject/<int:item_id>", methods=["POST"])
def dispatcher_reject(item_id):
    comment = request.form.get("comment", "").strip()

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    UPDATE fuel_transactions
    SET dispatcher_status='rejected',
        closed=FALSE,
        comment=%s
    WHERE id=%s
    """, (comment, item_id))

    conn.commit()
    cur.close()
    conn.close()
    return redirect("/")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
