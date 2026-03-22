import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, request, redirect

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_connection():
    return psycopg2.connect(DATABASE_URL, sslmode="require")


# ================= DB INIT =================

def init_tables():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS vehicles (
        id SERIAL PRIMARY KEY,
        vehicle_name VARCHAR(100),
        plate_number VARCHAR(30),
        company_name VARCHAR(150),
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS fuel_transactions (
        id SERIAL PRIMARY KEY,
        vehicle VARCHAR(100),
        object_name VARCHAR(100),
        entry_type VARCHAR(20), -- internal / external
        liters NUMERIC,
        odometer INTEGER,
        entered_by VARCHAR(100),

        manager_status VARCHAR(20) DEFAULT 'new',
        fueled BOOLEAN DEFAULT FALSE,
        driver_confirmed BOOLEAN DEFAULT FALSE,
        dispatcher_status VARCHAR(20) DEFAULT 'new',
        closed BOOLEAN DEFAULT FALSE,

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
        cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type_sql}")
        conn.commit()

    cur.close()
    conn.close()


def ensure_schema():
    ensure_column("fuel_transactions", "manager_status", "VARCHAR(20) DEFAULT 'new'")
    ensure_column("fuel_transactions", "fueled", "BOOLEAN DEFAULT FALSE")
    ensure_column("fuel_transactions", "driver_confirmed", "BOOLEAN DEFAULT FALSE")
    ensure_column("fuel_transactions", "dispatcher_status", "VARCHAR(20) DEFAULT 'new'")
    ensure_column("fuel_transactions", "closed", "BOOLEAN DEFAULT FALSE")
    ensure_column("fuel_transactions", "comment", "TEXT")
    ensure_column("vehicles", "company_name", "VARCHAR(150)")


()
ensure_schema()


# ================= HELPERS =================

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


def execute(query, params=None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(query, params or ())
    conn.commit()
    cur.close()
    conn.close()


def safe(v):
    return "" if v is None else str(v)


def badge(text, cls="gray"):
    return f'<span class="badge {cls}">{text}</span>'


def status_text(item):
    if item["entry_type"] == "external":
        if item["dispatcher_status"] == "rejected":
            return badge("Отклонено АТС", "red")
        if item["closed"]:
            return badge("Закрыто", "green")
        return badge("Ожидает проверки АТС", "yellow")

    if item["manager_status"] == "rejected":
        return badge("Отклонено руководителем", "red")
    if item["dispatcher_status"] == "rejected":
        return badge("Отклонено АТС", "red")
    if item["closed"]:
        return badge("Закрыто", "green")
    if item["manager_status"] == "new":
        return badge("Ожидает согласования", "yellow")
    if item["manager_status"] == "approved" and not item["fueled"]:
        return badge("Ожидает выдачи топлива", "blue")
    if item["fueled"] and not item["driver_confirmed"]:
        return badge("Ожидает подтверждения водителя", "purple")
    if item["fueled"] and item["driver_confirmed"] and not item["closed"]:
        return badge("Ожидает проверки АТС", "yellow")
    return badge("В процессе", "gray")


def render_layout(title, content, active="dashboard"):
    nav = f"""
    <div class="topbar">
        <div class="brand">⛽ Система учета ГСМ</div>
        <div class="nav">
            <a class="{ 'active' if active == 'dashboard' else '' }" href="/">Главная</a>
            <a class="{ 'active' if active == 'new' else '' }" href="/new">Новая запись</a>
            <a class="{ 'active' if active == 'requester' else '' }" href="/role/requester">Заявитель</a>
            <a class="{ 'active' if active == 'manager' else '' }" href="/role/manager">Руководитель</a>
            <a class="{ 'active' if active == 'fueler' else '' }" href="/role/fueler">Заправщик</a>
            <a class="{ 'active' if active == 'driver' else '' }" href="/role/driver">Водитель</a>
            <a class="{ 'active' if active == 'dispatcher' else '' }" href="/role/dispatcher">АТС</a>
            <a class="{ 'active' if active == 'vehicles' else '' }" href="/vehicles">Транспорт</a>
            <a class="{ 'active' if active == 'journal' else '' }" href="/journal">Журнал</a>
        </div>
    </div>
    """

    return f"""
    <html>
    <head>
        <meta charset="UTF-8">
        <title>{title}</title>
        <style>
            * {{
                box-sizing: border-box;
            }}
            body {{
                margin: 0;
                font-family: Arial, sans-serif;
                background: #f3f6fb;
                color: #1f2937;
            }}
            .topbar {{
                background: linear-gradient(135deg, #0f172a, #1e293b);
                color: white;
                padding: 16px 22px;
                box-shadow: 0 2px 12px rgba(0,0,0,0.18);
                position: sticky;
                top: 0;
                z-index: 100;
            }}
            .brand {{
                font-size: 22px;
                font-weight: 700;
                margin-bottom: 12px;
            }}
            .nav {{
                display: flex;
                flex-wrap: wrap;
                gap: 10px;
            }}
            .nav a {{
                text-decoration: none;
                color: #e5e7eb;
                padding: 9px 14px;
                border-radius: 10px;
                background: rgba(255,255,255,0.08);
                font-size: 14px;
            }}
            .nav a.active {{
                background: white;
                color: #0f172a;
                font-weight: bold;
            }}
            .container {{
                max-width: 1400px;
                margin: 24px auto;
                padding: 0 16px;
            }}
            .page-title {{
                font-size: 28px;
                font-weight: 700;
                margin-bottom: 18px;
            }}
            .sub {{
                color: #64748b;
                margin-top: -8px;
                margin-bottom: 20px;
            }}
            .grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
                gap: 16px;
                margin-bottom: 24px;
            }}
            .stat {{
                background: white;
                border-radius: 16px;
                padding: 18px;
                box-shadow: 0 6px 20px rgba(15, 23, 42, 0.08);
            }}
            .stat .label {{
                color: #64748b;
                font-size: 13px;
                margin-bottom: 8px;
            }}
            .stat .value {{
                font-size: 28px;
                font-weight: 700;
            }}
            .card {{
                background: white;
                border-radius: 18px;
                padding: 18px;
                box-shadow: 0 6px 20px rgba(15, 23, 42, 0.08);
                margin-bottom: 18px;
            }}
            .record {{
                border: 1px solid #e5e7eb;
                border-radius: 16px;
                padding: 16px;
                margin-bottom: 14px;
                background: #fcfdff;
            }}
            .record-header {{
                display: flex;
                justify-content: space-between;
                align-items: start;
                gap: 12px;
                margin-bottom: 12px;
                flex-wrap: wrap;
            }}
            .record-title {{
                font-size: 20px;
                font-weight: 700;
            }}
            .muted {{
                color: #64748b;
                font-size: 14px;
            }}
            .meta {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 10px;
                margin: 12px 0;
            }}
            .meta-item {{
                background: #f8fafc;
                border-radius: 12px;
                padding: 10px 12px;
                border: 1px solid #e2e8f0;
            }}
            .meta-item b {{
                display: block;
                font-size: 12px;
                color: #64748b;
                margin-bottom: 5px;
            }}
            .actions {{
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
                margin-top: 12px;
            }}
            .actions form {{
                margin: 0;
            }}
            input, select, textarea {{
                width: 100%;
                padding: 11px 12px;
                border: 1px solid #cbd5e1;
                border-radius: 12px;
                font-size: 14px;
                background: white;
            }}
            textarea {{
                min-height: 90px;
                resize: vertical;
            }}
            .form-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
                gap: 14px;
            }}
            button {{
                border: none;
                border-radius: 12px;
                padding: 10px 14px;
                cursor: pointer;
                font-weight: 600;
                font-size: 14px;
            }}
            .btn-primary {{
                background: #2563eb;
                color: white;
            }}
            .btn-success {{
                background: #16a34a;
                color: white;
            }}
            .btn-warning {{
                background: #d97706;
                color: white;
            }}
            .btn-danger {{
                background: #dc2626;
                color: white;
            }}
            .btn-gray {{
                background: #475569;
                color: white;
            }}
            .badge {{
                display: inline-block;
                padding: 6px 10px;
                border-radius: 999px;
                font-size: 12px;
                font-weight: 700;
            }}
            .badge.gray {{
                background: #e5e7eb;
                color: #334155;
            }}
            .badge.green {{
                background: #dcfce7;
                color: #166534;
            }}
            .badge.red {{
                background: #fee2e2;
                color: #991b1b;
            }}
            .badge.yellow {{
                background: #fef3c7;
                color: #92400e;
            }}
            .badge.blue {{
                background: #dbeafe;
                color: #1d4ed8;
            }}
            .badge.purple {{
                background: #ede9fe;
                color: #6d28d9;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
            }}
            th, td {{
                text-align: left;
                padding: 12px;
                border-bottom: 1px solid #e5e7eb;
                font-size: 14px;
                vertical-align: top;
            }}
            th {{
                background: #f8fafc;
                color: #475569;
            }}
            .empty {{
                padding: 30px;
                text-align: center;
                color: #64748b;
                background: white;
                border-radius: 18px;
                box-shadow: 0 6px 20px rgba(15, 23, 42, 0.08);
            }}
        </style>
    </head>
    <body>
        {nav}
        <div class="container">
            {content}
        </div>
    </body>
    </html>
    """


def render_record(item, role=None):
    title = f"{safe(item['vehicle'])} — {safe(item['liters'])} л"
    type_text = "Внутренний объект" if item["entry_type"] == "internal" else "Внешний объект"
    comment_html = ""
    if item["comment"]:
        comment_html = f"""
        <div class="meta-item" style="grid-column: 1 / -1;">
            <b>Комментарий</b>
            {safe(item["comment"])}
        </div>
        """

    actions = ""

    if role == "manager":
        actions = f"""
        <div class="actions">
            <form method="post" action="/manager_approve/{item['id']}">
                <button class="btn-success">Подтвердить заявку</button>
            </form>
            <form method="post" action="/manager_reject/{item['id']}">
                <input type="text" name="comment" placeholder="Причина отказа" required>
                <button class="btn-danger">Отклонить</button>
            </form>
        </div>
        """
    elif role == "fueler":
        actions = f"""
        <div class="actions">
            <form method="post" action="/fuel/{item['id']}">
                <button class="btn-primary">Выдать топливо</button>
            </form>
        </div>
        """
    elif role == "driver":
        actions = f"""
        <div class="actions">
            <form method="post" action="/driver/{item['id']}">
                <button class="btn-success">Подтвердить получение</button>
            </form>
        </div>
        """
    elif role == "dispatcher":
        actions = f"""
        <div class="actions">
            <form method="post" action="/close/{item['id']}">
                <button class="btn-success">Закрыть операцию</button>
            </form>
            <form method="post" action="/dispatcher_reject/{item['id']}">
                <input type="text" name="comment" placeholder="Причина отказа АТС" required>
                <button class="btn-danger">Отклонить АТС</button>
            </form>
        </div>
        """

    return f"""
    <div class="record">
        <div class="record-header">
            <div>
                <div class="record-title">{title}</div>
                <div class="muted">ID: {item['id']} | {type_text}</div>
            </div>
            <div>{status_text(item)}</div>
        </div>

        <div class="meta">
            <div class="meta-item"><b>Объект</b>{safe(item['object_name'])}</div>
            <div class="meta-item"><b>Одометр</b>{safe(item['odometer'])}</div>
            <div class="meta-item"><b>Кто внес</b>{safe(item['entered_by'])}</div>
            <div class="meta-item"><b>Дата</b>{safe(item['created_at'])}</div>
            {comment_html}
        </div>

        {actions}
    </div>
    """


# ================= DASHBOARD =================

@app.route("/")
def dashboard():
    stats = {
        "all": fetch_all("SELECT COUNT(*) AS cnt FROM fuel_transactions")[0]["cnt"],
        "manager": fetch_all("""
            SELECT COUNT(*) AS cnt
            FROM fuel_transactions
            WHERE entry_type='internal' AND manager_status='new'
        """)[0]["cnt"],
        "fueler": fetch_all("""
            SELECT COUNT(*) AS cnt
            FROM fuel_transactions
            WHERE entry_type='internal' AND manager_status='approved' AND fueled=FALSE
        """)[0]["cnt"],
        "driver": fetch_all("""
            SELECT COUNT(*) AS cnt
            FROM fuel_transactions
            WHERE entry_type='internal' AND manager_status='approved' AND fueled=TRUE AND driver_confirmed=FALSE
        """)[0]["cnt"],
        "dispatcher": fetch_all("""
            SELECT COUNT(*) AS cnt
            FROM fuel_transactions
            WHERE (
                entry_type='external' AND dispatcher_status='new' AND closed=FALSE
            ) OR (
                entry_type='internal' AND manager_status='approved' AND fueled=TRUE AND driver_confirmed=TRUE AND dispatcher_status='new' AND closed=FALSE
            )
        """)[0]["cnt"],
        "closed": fetch_all("""
            SELECT COUNT(*) AS cnt
            FROM fuel_transactions
            WHERE closed=TRUE
        """)[0]["cnt"],
    }

    content = f"""
    <div class="page-title">Главная</div>
    <div class="sub">Быстрый переход по ролям и текущим задачам</div>

    <div class="grid">
        <div class="stat"><div class="label">Всего операций</div><div class="value">{stats['all']}</div></div>
        <div class="stat"><div class="label">Ожидают руководителя</div><div class="value">{stats['manager']}</div></div>
        <div class="stat"><div class="label">Ожидают заправщика</div><div class="value">{stats['fueler']}</div></div>
        <div class="stat"><div class="label">Ожидают водителя</div><div class="value">{stats['driver']}</div></div>
        <div class="stat"><div class="label">Ожидают АТС</div><div class="value">{stats['dispatcher']}</div></div>
        <div class="stat"><div class="label">Закрытые операции</div><div class="value">{stats['closed']}</div></div>
    </div>

    <div class="grid">
        <div class="card">
            <h3>Для заявителя</h3>
            <p>Создание новой заявки и просмотр своих записей.</p>
            <a href="/new"><button class="btn-primary">Создать заявку</button></a>
            <a href="/role/requester"><button class="btn-gray">Открыть раздел</button></a>
        </div>
        <div class="card">
            <h3>Для руководителя</h3>
            <p>Подтверждение или отклонение заявок.</p>
            <a href="/role/manager"><button class="btn-warning">Открыть задачи</button></a>
        </div>
        <div class="card">
            <h3>Для заправщика</h3>
            <p>Только заявки на выдачу топлива.</p>
            <a href="/role/fueler"><button class="btn-primary">Открыть задачи</button></a>
        </div>
        <div class="card">
            <h3>Для водителя</h3>
            <p>Подтверждение фактического получения топлива.</p>
            <a href="/role/driver"><button class="btn-success">Открыть задачи</button></a>
        </div>
        <div class="card">
            <h3>Для АТС</h3>
            <p>Проверка операций и управление транспортом.</p>
            <a href="/role/dispatcher"><button class="btn-danger">Открыть задачи</button></a>
            <a href="/vehicles"><button class="btn-gray">Транспорт</button></a>
        </div>
    </div>
    """
    return render_layout("Главная", content, active="dashboard")


# ================= NEW ENTRY =================

@app.route("/new", methods=["GET", "POST"])
def new_entry():
    if request.method == "POST":
        vehicle = request.form.get("vehicle", "").strip()
        object_name = request.form.get("object", "").strip()
        entry_type = request.form.get("entry_type", "").strip()
        liters = request.form.get("liters", "").strip()
        odometer = request.form.get("odometer", "").strip()
        entered_by = request.form.get("entered_by", "").strip()

        if vehicle and entry_type and liters and entered_by:
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

            if entry_type == "external":
                manager_status = "approved"
                fueled = True
                driver_confirmed = True
            else:
                manager_status = "new"
                fueled = False
                driver_confirmed = False

            execute("""
                INSERT INTO fuel_transactions (
                    vehicle, object_name, entry_type, liters, odometer, entered_by,
                    manager_status, fueled, driver_confirmed, dispatcher_status, closed, comment
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'new', FALSE, NULL)
            """, (
                vehicle, object_name, entry_type, liters_value, odometer_value, entered_by,
                manager_status, fueled, driver_confirmed
            ))
        return redirect("/role/requester")

    vehicles = fetch_all("""
        SELECT vehicle_name, plate_number, company_name
        FROM vehicles
        WHERE is_active=TRUE
        ORDER BY vehicle_name
    """)

    options = "<option value=''>Выберите транспорт</option>"
    for v in vehicles:
        title = safe(v["vehicle_name"])
        plate = safe(v["plate_number"])
        company = safe(v["company_name"])
        label = f"{title} | {plate} | {company}"
        options += f"<option value='{title}'>{label}</option>"

    content = f"""
    <div class="page-title">Новая запись</div>
    <div class="sub">Создание заявки на заправку</div>

    <div class="card">
        <form method="post">
            <div class="form-grid">
                <div>
                    <label>Транспорт</label>
                    <select name="vehicle" required>{options}</select>
                </div>
                <div>
                    <label>Объект</label>
                    <input name="object" placeholder="Введите объект">
                </div>
                <div>
                    <label>Тип операции</label>
                    <select name="entry_type" required>
                        <option value="internal">Внутренний объект</option>
                        <option value="external">Внешний объект</option>
                    </select>
                </div>
                <div>
                    <label>Объем топлива (л)</label>
                    <input name="liters" type="number" step="0.01" placeholder="Например 120" required>
                </div>
                <div>
                    <label>Одометр</label>
                    <input name="odometer" type="number" placeholder="Например 152340">
                </div>
                <div>
                    <label>Кто внес запись</label>
                    <input name="entered_by" placeholder="ФИО" required>
                </div>
            </div>

            <div style="margin-top:16px;">
                <button class="btn-primary" type="submit">Сохранить запись</button>
            </div>
        </form>
    </div>
    """
    return render_layout("Новая запись", content, active="new")


# ================= ROLE PAGES =================

@app.route("/role/requester")
def role_requester():
    q = request.args.get("q", "").strip()
    query = "SELECT * FROM fuel_transactions"
    params = []

    if q:
        query += """
        WHERE entered_by ILIKE %s
           OR vehicle ILIKE %s
           OR object_name ILIKE %s
        """
        like = f"%{q}%"
        params = [like, like, like]

    query += " ORDER BY id DESC"
    items = fetch_all(query, params)

    records = "".join(render_record(item) for item in items) if items else '<div class="empty">Записей не найдено</div>'

    content = f"""
    <div class="page-title">Раздел заявителя</div>
    <div class="sub">Здесь можно смотреть созданные заявки и их текущее состояние</div>

    <div class="card">
        <form method="get">
            <div class="form-grid">
                <div>
                    <label>Поиск по ФИО, транспорту или объекту</label>
                    <input name="q" value="{safe(q)}" placeholder="Например: Иванов или КамАЗ">
                </div>
            </div>
            <div style="margin-top:14px;">
                <button class="btn-primary" type="submit">Найти</button>
                <a href="/new"><button class="btn-success" type="button">Создать новую заявку</button></a>
            </div>
        </form>
    </div>

    {records}
    """
    return render_layout("Заявитель", content, active="requester")


@app.route("/role/manager")
def role_manager():
    items = fetch_all("""
        SELECT *
        FROM fuel_transactions
        WHERE entry_type='internal' AND manager_status='new'
        ORDER BY id DESC
    """)
    records = "".join(render_record(item, role="manager") for item in items) if items else '<div class="empty">Нет заявок на согласование</div>'

    content = f"""
    <div class="page-title">Раздел руководителя</div>
    <div class="sub">Показываются только заявки, ожидающие согласования</div>
    {records}
    """
    return render_layout("Руководитель", content, active="manager")


@app.route("/role/fueler")
def role_fueler():
    items = fetch_all("""
        SELECT *
        FROM fuel_transactions
        WHERE entry_type='internal'
          AND manager_status='approved'
          AND fueled=FALSE
          AND closed=FALSE
        ORDER BY id DESC
    """)
    records = "".join(render_record(item, role="fueler") for item in items) if items else '<div class="empty">Нет заявок на выдачу топлива</div>'

    content = f"""
    <div class="page-title">Раздел заправщика</div>
    <div class="sub">Показываются только заявки, по которым нужно выдать топливо</div>
    {records}
    """
    return render_layout("Заправщик", content, active="fueler")


@app.route("/role/driver")
def role_driver():
    items = fetch_all("""
        SELECT *
        FROM fuel_transactions
        WHERE entry_type='internal'
          AND manager_status='approved'
          AND fueled=TRUE
          AND driver_confirmed=FALSE
          AND closed=FALSE
        ORDER BY id DESC
    """)
    records = "".join(render_record(item, role="driver") for item in items) if items else '<div class="empty">Нет операций для подтверждения водителем</div>'

    content = f"""
    <div class="page-title">Раздел водителя</div>
    <div class="sub">Показываются только записи, по которым водитель должен подтвердить получение топлива</div>
    {records}
    """
    return render_layout("Водитель", content, active="driver")


@app.route("/role/dispatcher")
def role_dispatcher():
    items = fetch_all("""
        SELECT *
        FROM fuel_transactions
        WHERE (
            entry_type='external'
            AND dispatcher_status='new'
            AND closed=FALSE
        )
        OR (
            entry_type='internal'
            AND manager_status='approved'
            AND fueled=TRUE
            AND driver_confirmed=TRUE
            AND dispatcher_status='new'
            AND closed=FALSE
        )
        ORDER BY id DESC
    """)
    records = "".join(render_record(item, role="dispatcher") for item in items) if items else '<div class="empty">Нет операций для проверки АТС</div>'

    content = f"""
    <div class="page-title">Раздел АТС</div>
    <div class="sub">Финальная проверка и закрытие операций. Также АТС может управлять транспортом.</div>

    <div style="margin-bottom:16px;">
        <a href="/vehicles"><button class="btn-gray">Перейти в раздел транспорта</button></a>
    </div>

    {records}
    """
    return render_layout("АТС", content, active="dispatcher")


# ================= JOURNAL =================

@app.route("/journal")
def journal():
    items = fetch_all("""
        SELECT *
        FROM fuel_transactions
        ORDER BY id DESC
    """)

    rows = ""
    for item in items:
        rows += f"""
        <tr>
            <td>{item['id']}</td>
            <td>{safe(item['vehicle'])}</td>
            <td>{safe(item['object_name'])}</td>
            <td>{"Внутренний" if item['entry_type'] == 'internal' else "Внешний"}</td>
            <td>{safe(item['liters'])}</td>
            <td>{safe(item['odometer'])}</td>
            <td>{safe(item['entered_by'])}</td>
            <td>{status_text(item)}</td>
            <td>{safe(item['comment'])}</td>
        </tr>
        """

    if not rows:
        rows = '<tr><td colspan="9">Нет записей</td></tr>'

    content = f"""
    <div class="page-title">Общий журнал</div>
    <div class="sub">Полный список всех операций</div>

    <div class="card">
        <table>
            <tr>
                <th>ID</th>
                <th>Транспорт</th>
                <th>Объект</th>
                <th>Тип</th>
                <th>Литры</th>
                <th>Одометр</th>
                <th>Кто внес</th>
                <th>Статус</th>
                <th>Комментарий</th>
            </tr>
            {rows}
        </table>
    </div>
    """
    return render_layout("Журнал", content, active="journal")


# ================= VEHICLES =================

@app.route("/vehicles", methods=["GET", "POST"])
def vehicles():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        plate = request.form.get("plate", "").strip()
        company = request.form.get("company", "").strip()

        if name:
            execute("""
                INSERT INTO vehicles (vehicle_name, plate_number, company_name, is_active)
                VALUES (%s, %s, %s, TRUE)
            """, (name, plate, company))

        return redirect("/vehicles")

    rows = fetch_all("""
        SELECT *
        FROM vehicles
        ORDER BY id DESC
    """)

    table_rows = ""
    for r in rows:
        status = badge("Активен", "green") if r["is_active"] else badge("Неактивен", "red")

        table_rows += f"""
        <tr>
            <td>{r['id']}</td>
            <td>{safe(r['vehicle_name'])}</td>
            <td>{safe(r['plate_number'])}</td>
            <td>{safe(r['company_name'])}</td>
            <td>{status}</td>
            <td>
                <a href="/vehicles/edit/{r['id']}"><button class="btn-primary" type="button">Редактировать</button></a>
                <form method="post" action="/vehicles/toggle/{r['id']}" style="display:inline-block;">
                    <button class="btn-gray" type="submit">
                        {"Сделать неактивным" if r["is_active"] else "Сделать активным"}
                    </button>
                </form>
            </td>
        </tr>
        """

    if not table_rows:
        table_rows = '<tr><td colspan="6">Транспорт пока не добавлен</td></tr>'

    content = f"""
    <div class="page-title">Транспорт</div>
    <div class="sub">АТС может добавлять, редактировать и отключать транспорт</div>

    <div class="card">
        <h3>Добавить транспорт</h3>
        <form method="post">
            <div class="form-grid">
                <div>
                    <label>Наименование</label>
                    <input name="name" placeholder="Например: КамАЗ 6520" required>
                </div>
                <div>
                    <label>Госномер</label>
                    <input name="plate" placeholder="Например: 01 A 123 BC">
                </div>
                <div>
                    <label>Компания</label>
                    <input name="company" placeholder="Например: ООО Нефтесервис">
                </div>
            </div>
            <div style="margin-top:16px;">
                <button class="btn-success" type="submit">Добавить транспорт</button>
            </div>
        </form>
    </div>

    <div class="card">
        <h3>Список транспорта</h3>
        <table>
            <tr>
                <th>ID</th>
                <th>Наименование</th>
                <th>Госномер</th>
                <th>Компания</th>
                <th>Статус</th>
                <th>Действия</th>
            </tr>
            {table_rows}
        </table>
    </div>
    """
    return render_layout("Транспорт", content, active="vehicles")


@app.route("/vehicles/edit/<int:vehicle_id>", methods=["GET", "POST"])
def edit_vehicle(vehicle_id):
    vehicle = fetch_one("""
        SELECT *
        FROM vehicles
        WHERE id=%s
    """, (vehicle_id,))

    if not vehicle:
        return redirect("/vehicles")

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        plate = request.form.get("plate", "").strip()
        company = request.form.get("company", "").strip()
        is_active = request.form.get("is_active") == "true"

        if name:
            execute("""
                UPDATE vehicles
                SET vehicle_name=%s,
                    plate_number=%s,
                    company_name=%s,
                    is_active=%s
                WHERE id=%s
            """, (name, plate, company, is_active, vehicle_id))

        return redirect("/vehicles")

    checked_true = "selected" if vehicle["is_active"] else ""
    checked_false = "selected" if not vehicle["is_active"] else ""

    content = f"""
    <div class="page-title">Редактирование транспорта</div>
    <div class="sub">Здесь можно изменить название, госномер, объект и статус транспорта</div>

    <div class="card">
        <form method="post">
            <div class="form-grid">
                <div>
                    <label>Наименование</label>
                    <input name="name" value="{safe(vehicle['vehicle_name'])}" required>
                </div>
                <div>
                    <label>Госномер</label>
                    <input name="plate" value="{safe(vehicle['plate_number'])}">
                </div>
                <div>
                    <label>Компания</label>
                    <input name="company" value="{safe(vehicle['company_name'])}">
                </div>
                <div>
                    <label>Статус</label>
                    <select name="is_active">
                        <option value="true" {checked_true}>Активен</option>
                        <option value="false" {checked_false}>Неактивен</option>
                    </select>
                </div>
            </div>

            <div style="margin-top:16px;" class="actions">
                <button class="btn-primary" type="submit">Сохранить изменения</button>
                <a href="/vehicles"><button class="btn-gray" type="button">Назад</button></a>
            </div>
        </form>
    </div>
    """
    return render_layout("Редактирование транспорта", content, active="vehicles")


@app.route("/vehicles/toggle/<int:vehicle_id>", methods=["POST"])
def toggle_vehicle(vehicle_id):
    vehicle = fetch_one("""
        SELECT is_active
        FROM vehicles
        WHERE id=%s
    """, (vehicle_id,))

    if vehicle:
        new_status = not vehicle["is_active"]
        execute("""
            UPDATE vehicles
            SET is_active=%s
            WHERE id=%s
        """, (new_status, vehicle_id))

    return redirect("/vehicles")


# ================= ACTIONS =================

@app.route("/manager_approve/<int:item_id>", methods=["POST"])
def manager_approve(item_id):
    execute("""
        UPDATE fuel_transactions
        SET manager_status='approved',
            comment=NULL
        WHERE id=%s
    """, (item_id,))
    return redirect("/role/manager")


@app.route("/manager_reject/<int:item_id>", methods=["POST"])
def manager_reject(item_id):
    comment = request.form.get("comment", "").strip()
    execute("""
        UPDATE fuel_transactions
        SET manager_status='rejected',
            comment=%s
        WHERE id=%s
    """, (comment, item_id))
    return redirect("/role/manager")


@app.route("/fuel/<int:item_id>", methods=["POST"])
def fuel(item_id):
    execute("""
        UPDATE fuel_transactions
        SET fueled=TRUE,
            comment=NULL
        WHERE id=%s
          AND manager_status='approved'
    """, (item_id,))
    return redirect("/role/fueler")


@app.route("/driver/<int:item_id>", methods=["POST"])
def driver(item_id):
    execute("""
        UPDATE fuel_transactions
        SET driver_confirmed=TRUE,
            comment=NULL
        WHERE id=%s
          AND fueled=TRUE
    """, (item_id,))
    return redirect("/role/driver")


@app.route("/close/<int:item_id>", methods=["POST"])
def close_operation(item_id):
    execute("""
        UPDATE fuel_transactions
        SET closed=TRUE,
            dispatcher_status='approved',
            comment=NULL
        WHERE id=%s
    """, (item_id,))
    return redirect("/role/dispatcher")


@app.route("/dispatcher_reject/<int:item_id>", methods=["POST"])
def dispatcher_reject(item_id):
    comment = request.form.get("comment", "").strip()
    execute("""
        UPDATE fuel_transactions
        SET dispatcher_status='rejected',
            closed=FALSE,
            comment=%s
        WHERE id=%s
    """, (comment, item_id))
    return redirect("/role/dispatcher")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
