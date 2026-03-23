from flask import Blueprint, request, redirect
from auth import login_required
from layout import render_page
from db import fetch_all, fetch_one, execute_query

vehicles_bp = Blueprint("vehicles_bp", __name__)


@vehicles_bp.route("/vehicles")
@login_required
def vehicles_page():
    rows = fetch_all("""
        SELECT v.id, v.brand, v.vehicle_type, v.plate_number, c.name AS company_name
        FROM vehicles v
        LEFT JOIN companies c ON c.id = v.company_id
        ORDER BY v.id DESC
    """)

    content = "<h2>Транспорт</h2>"

    content += "<p><a href='/vehicles/new'>➕ Добавить транспорт</a></p>"

    if rows:
        content += """
        <table border='1' cellpadding='8' cellspacing='0' style='border-collapse: collapse; width:100%;'>
            <tr>
                <th>ID</th>
                <th>Марка</th>
                <th>Тип</th>
                <th>Гос.номер</th>
                <th>Компания</th>
                <th>Действия</th>
            </tr>
        """
        for row in rows:
            content += f"""
            <tr>
                <td>{row['id']}</td>
                <td>{row['brand'] or ''}</td>
                <td>{row['vehicle_type'] or ''}</td>
                <td>{row['plate_number'] or ''}</td>
                <td>{row['company_name'] or ''}</td>
                <td><a href='/vehicles/edit/{row["id"]}'>✏️ Редактировать</a></td>
            </tr>
            """
        content += "</table>"
    else:
        content += "<p>Транспорт пока не добавлен.</p>"

    return render_page("Транспорт", content)


@vehicles_bp.route("/vehicles/new", methods=["GET", "POST"])
@login_required
def vehicles_new():
    if request.method == "POST":
        brand = request.form.get("brand", "").strip()
        vehicle_type = request.form.get("vehicle_type", "").strip()
        plate_number = request.form.get("plate_number", "").strip().upper()
        company_id = request.form.get("company_id") or None

        execute_query("""
            INSERT INTO vehicles (brand, vehicle_type, plate_number, company_id)
            VALUES (%s, %s, %s, %s)
        """, (brand, vehicle_type, plate_number, company_id))

        return redirect("/vehicles")

    companies = fetch_all("SELECT id, name FROM companies ORDER BY name")

    content = "<h2>Добавить транспорт</h2>"
    content += "<form method='post'>"

    content += "<label>Марка:</label><br>"
    content += "<input type='text' name='brand' required><br><br>"

    content += "<label>Тип транспорта:</label><br>"
    content += "<input type='text' name='vehicle_type' required><br><br>"

    content += "<label>Гос.номер:</label><br>"
    content += "<input type='text' name='plate_number' required><br><br>"

    content += "<label>Компания:</label><br>"
    content += "<select name='company_id' required>"
    content += "<option value=''>-- Выберите --</option>"
    for c in companies:
        content += f"<option value='{c['id']}'>{c['name']}</option>"
    content += "</select><br><br>"

    content += "<button type='submit'>Сохранить</button> "
    content += "<a href='/vehicles'>Отмена</a>"

    content += "</form>"

    return render_page("Добавить транспорт", content)


@vehicles_bp.route("/vehicles/edit/<int:vehicle_id>", methods=["GET", "POST"])
@login_required
def vehicles_edit(vehicle_id):
    vehicle = fetch_one("SELECT * FROM vehicles WHERE id = %s", (vehicle_id,))
    if not vehicle:
        return render_page("Ошибка", "<p>Транспорт не найден.</p>")

    if request.method == "POST":
        brand = request.form.get("brand", "").strip()
        vehicle_type = request.form.get("vehicle_type", "").strip()
        plate_number = request.form.get("plate_number", "").strip().upper()
        company_id = request.form.get("company_id") or None

        execute_query("""
            UPDATE vehicles
            SET brand = %s,
                vehicle_type = %s,
                plate_number = %s,
                company_id = %s
            WHERE id = %s
        """, (brand, vehicle_type, plate_number, company_id, vehicle_id))

        return redirect("/vehicles")

    companies = fetch_all("SELECT id, name FROM companies ORDER BY name")

    content = "<h2>Редактировать транспорт</h2>"
    content += "<form method='post'>"

    content += "<label>Марка:</label><br>"
    content += f"<input type='text' name='brand' value='{vehicle['brand'] or ''}' required><br><br>"

    content += "<label>Тип транспорта:</label><br>"
    content += f"<input type='text' name='vehicle_type' value='{vehicle['vehicle_type'] or ''}' required><br><br>"

    content += "<label>Гос.номер:</label><br>"
    content += f"<input type='text' name='plate_number' value='{vehicle['plate_number'] or ''}' required><br><br>"

    content += "<label>Компания:</label><br>"
    content += "<select name='company_id' required>"
    content += "<option value=''>-- Выберите --</option>"
    for c in companies:
        selected = "selected" if vehicle["company_id"] == c["id"] else ""
        content += f"<option value='{c['id']}' {selected}>{c['name']}</option>"
    content += "</select><br><br>"

    content += "<button type='submit'>Сохранить</button> "
    content += "<a href='/vehicles'>Назад</a>"

    content += "</form>"

    return render_page("Редактировать транспорт", content)
