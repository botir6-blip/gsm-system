from flask import Blueprint, request, redirect
from auth import login_required
from layout import render_page
from db import fetch_all, execute_query

requests_bp = Blueprint("requests_bp", __name__)


# 📋 Заявкалар рўйхати
@requests_bp.route("/requests")
@login_required
def requests_page():
    rows = fetch_all("""
        SELECT r.id,
               v.plate_number,
               o.name AS object_name,
               r.liters,
               r.status,
               r.created_at
        FROM fuel_requests r
        LEFT JOIN vehicles v ON v.id = r.vehicle_id
        LEFT JOIN objects o ON o.id = r.object_id
        ORDER BY r.id DESC
    """)

    content = "<h2>Заявки</h2>"

    if rows:
        content += """
        <table border='1' cellpadding='8' style='border-collapse: collapse; width:100%;'>
            <tr>
                <th>ID</th>
                <th>Транспорт</th>
                <th>Объект</th>
                <th>Литры</th>
                <th>Статус</th>
                <th>Дата</th>
            </tr>
        """
        for r in rows:
            content += f"""
            <tr>
                <td>{r['id']}</td>
                <td>{r['plate_number'] or ''}</td>
                <td>{r['object_name'] or ''}</td>
                <td>{r['liters']}</td>
                <td>{r['status']}</td>
                <td>{r['created_at']}</td>
            </tr>
            """
        content += "</table>"
    else:
        content += "<p>Заявок пока нет.</p>"

    content += "<br><a href='/requests/new'>➕ Новая заявка</a>"

    return render_page("Заявки", content)


# ➕ Янги заявка
@requests_bp.route("/requests/new", methods=["GET", "POST"])
@login_required
def new_request():
    if request.method == "POST":
        vehicle_id = request.form.get("vehicle_id")
        object_id = request.form.get("object_id")
        liters = request.form.get("liters")

        execute_query("""
            INSERT INTO fuel_requests (vehicle_id, object_id, liters, status)
            VALUES (%s, %s, %s, 'new')
        """, (vehicle_id, object_id, liters))

        return redirect("/requests")

    # 🔽 dropdown учун маълумотлар
    vehicles = fetch_all("SELECT id, plate_number FROM vehicles ORDER BY plate_number")
    objects = fetch_all("SELECT id, name FROM objects ORDER BY name")

    content = "<h2>Новая заявка</h2>"

    content += "<form method='post'>"

    # 🚗 транспорт
    content += "<label>Транспорт:</label><br>"
    content += "<select name='vehicle_id'>"
    for v in vehicles:
        content += f"<option value='{v['id']}'>{v['plate_number']}</option>"
    content += "</select><br><br>"

    # 🏗 объект
    content += "<label>Объект:</label><br>"
    content += "<select name='object_id'>"
    for o in objects:
        content += f"<option value='{o['id']}'>{o['name']}</option>"
    content += "</select><br><br>"

    # ⛽ литр
    content += "<label>Литры:</label><br>"
    content += "<input type='number' name='liters'><br><br>"

    content += "<button type='submit'>Сохранить</button>"
    content += "</form>"

    return render_page("Новая заявка", content)
