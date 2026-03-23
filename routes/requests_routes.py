from flask import Blueprint, request, redirect
from auth import login_required
from layout import render_page
from db import fetch_all, execute_query

requests_bp = Blueprint("requests_bp", __name__)


@requests_bp.route("/requests")
@login_required
def requests_page():
    rows = fetch_all("""
        SELECT
            r.id,
            v.plate_number,
            o.name AS object_name,
            r.requested_liters,
            r.actual_liters,
            r.requested_by,
            r.status,
            r.created_at
        FROM fuel_requests r
        LEFT JOIN vehicles v ON v.id = r.vehicle_id
        LEFT JOIN objects o ON o.id = r.object_id
        ORDER BY r.id DESC
    """)

    content = "<h2>Заявки</h2>"
    content += "<p><a href='/requests/new'>➕ Новая заявка</a></p>"

    if rows:
        content += """
        <table border='1' cellpadding='8' cellspacing='0' style='border-collapse: collapse; width:100%;'>
            <tr>
                <th>ID</th>
                <th>Транспорт</th>
                <th>Объект</th>
                <th>Запрошено</th>
                <th>Факт</th>
                <th>Подал</th>
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
                <td>{r['requested_liters'] or ''}</td>
                <td>{r['actual_liters'] or ''}</td>
                <td>{r['requested_by'] or ''}</td>
                <td>{r['status'] or ''}</td>
                <td>{r['created_at'] or ''}</td>
            </tr>
            """
        content += "</table>"
    else:
        content += "<p>Заявок пока нет.</p>"

    return render_page("Заявки", content)

@requests_bp.route("/requests/new", methods=["GET", "POST"])
@login_required
def new_request():
    if request.method == "POST":
        object_id = request.form.get("object_id") or None
        vehicle_id = request.form.get("vehicle_id") or None
        requested_liters = request.form.get("requested_liters") or 0
        requested_by = request.form.get("requested_by") or ""
        project_name = request.form.get("project_name") or ""
        tank_balance = request.form.get("tank_balance") or ""
        route_work = request.form.get("route_work") or ""
        comment = request.form.get("comment") or ""

        full_comment = f"""Остаток в баке: {tank_balance}
Маршрут / объем работ: {route_work}
Комментарий: {comment}"""

        execute_query("""
            INSERT INTO fuel_requests (
                object_id,
                vehicle_id,
                requested_liters,
                requested_by,
                project_name,
                request_comment,
                status
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'new')
        """, (
            object_id,
            vehicle_id,
            requested_liters,
            requested_by,
            project_name,
            full_comment
        ))

        return redirect("/requests")

    objects = fetch_all("""
        SELECT id, name
        FROM objects
        ORDER BY name
    """)

    vehicles = fetch_all("""
        SELECT id, plate_number, brand, vehicle_type
        FROM vehicles
        ORDER BY plate_number
    """)

    users = fetch_all("""
        SELECT id, full_name
        FROM users
        ORDER BY full_name
    """)

    content = """
    <div style='max-width:650px; margin:0 auto;'>
        <h2 style='margin-bottom:18px;'>Новая заявка</h2>
        <form method='post' style='display:flex; flex-direction:column; gap:12px;'>

            <div>
                <label>1. Объект заправки:</label><br>
                <select name='object_id' required style='width:100%; padding:8px;'>
                    <option value=''>-- Выберите --</option>
    """

    for o in objects:
        content += f"<option value='{o['id']}'>{o['name']}</option>"

    content += """
                </select>
            </div>

            <div>
                <label>2. Транспорт:</label><br>
                <select name='vehicle_id' required style='width:100%; padding:8px;'>
                    <option value=''>-- Выберите --</option>
    """

    for v in vehicles:
        plate = v["plate_number"] or ""
        brand = v["brand"] or ""
        vtype = v["vehicle_type"] or ""
        content += f"<option value='{v['id']}'>{plate} | {brand} | {vtype}</option>"

    content += """
                </select>
            </div>

            <div>
                <label>3. Остаток в баке (л):</label><br>
                <input type='number' step='0.01' name='tank_balance' style='width:100%; padding:8px;'>
            </div>

            <div>
                <label>4. Запрашиваемое количество топлива (л):</label><br>
                <input type='number' step='0.01' name='requested_liters' required style='width:100%; padding:8px;'>
            </div>

            <div>
                <label>5. Маршрут / объем работ:</label><br>
                <input type='text' name='route_work' style='width:100%; padding:8px;'>
            </div>

            <div>
                <label>6. Кто подает заявку:</label><br>
                <select name='requested_by' required style='width:100%; padding:8px;'>
                    <option value=''>-- Выберите --</option>
    """

    for u in users:
        content += f"<option value='{u['full_name']}'>{u['full_name']}</option>"

    content += """
                </select>
            </div>

            <div>
                <label>7. Проект:</label><br>
                <input type='text' name='project_name' style='width:100%; padding:8px;'>
            </div>

            <div>
                <label>8. Комментарий:</label><br>
                <textarea name='comment' rows='4' style='width:100%; padding:8px;'></textarea>
            </div>

            <div style='margin-top:8px;'>
                <button type='submit' style='padding:10px 16px;'>Сохранить заявку</button>
                <a href='/requests' style='margin-left:12px;'>Назад</a>
            </div>

        </form>
    </div>
    """

    return render_page("Новая заявка", content)
