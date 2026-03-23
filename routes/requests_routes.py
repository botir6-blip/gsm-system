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
        requester_position = request.form.get("requester_position") or ""
        project_name = request.form.get("project_name") or ""
        fuel_supplier = request.form.get("fuel_supplier") or ""
        request_comment = request.form.get("request_comment") or ""

        execute_query("""
            INSERT INTO fuel_requests (
                object_id,
                vehicle_id,
                requested_liters,
                requested_by,
                requester_position,
                project_name,
                fuel_supplier,
                request_comment,
                status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'new')
        """, (
            object_id,
            vehicle_id,
            requested_liters,
            requested_by,
            requester_position,
            project_name,
            fuel_supplier,
            request_comment
        ))

        return redirect("/requests")

    objects = fetch_all("SELECT id, name FROM objects ORDER BY name")
    vehicles = fetch_all("""
        SELECT id, plate_number, brand
        FROM vehicles
        ORDER BY plate_number
    """)

    content = "<h2>Новая заявка</h2>"
    content += "<form method='post'>"

    content += "<label>Объект:</label><br>"
    content += "<select name='object_id' required>"
    content += "<option value=''>-- Выберите --</option>"
    for o in objects:
        content += f"<option value='{o['id']}'>{o['name']}</option>"
    content += "</select><br><br>"

    content += "<label>Транспорт:</label><br>"
    content += "<select name='vehicle_id' required>"
    content += "<option value=''>-- Выберите --</option>"
    for v in vehicles:
        plate = v['plate_number'] or ''
        brand = v['brand'] or ''
        content += f"<option value='{v['id']}'>{plate} {brand}</option>"
    content += "</select><br><br>"

    content += "<label>Запрашиваемый объем:</label><br>"
    content += "<input type='number' step='0.01' name='requested_liters' required><br><br>"

    content += "<label>Кто подает заявку:</label><br>"
    content += "<input type='text' name='requested_by' required><br><br>"

    content += "<label>Должность:</label><br>"
    content += "<input type='text' name='requester_position'><br><br>"

    content += "<label>Проект:</label><br>"
    content += "<input type='text' name='project_name'><br><br>"

    content += "<label>Поставщик топлива:</label><br>"
    content += "<input type='text' name='fuel_supplier'><br><br>"

    content += "<label>Комментарий:</label><br>"
    content += "<textarea name='request_comment' rows='4' style='width:100%;'></textarea><br><br>"

    content += "<button type='submit'>Сохранить заявку</button> "
    content += "<a href='/requests'>Назад</a>"

    content += "</form>"

    return render_page("Новая заявка", content)
