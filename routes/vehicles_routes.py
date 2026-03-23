from flask import Blueprint, request, redirect
from auth import login_required
from layout import render_page
from db import fetch_all, fetch_one, execute_query

vehicles_bp = Blueprint("vehicles_bp", __name__)


def meter_type_label(value):
    if value == "speedometer":
        return "Спидометр"
    if value == "motohours":
        return "Моточасы"
    return ""


def meter_unit(value):
    if value == "speedometer":
        return "л/100 км"
    if value == "motohours":
        return "л/моточас"
    return ""


@vehicles_bp.route("/vehicles")
@login_required
def vehicles_page():
    rows = fetch_all("""
        SELECT
            id,
            vehicle_name,
            plate_number,
            meter_type,
            base_consumption,
            load_coeff_empty,
            load_coeff_loaded,
            load_coeff_heavy
        FROM vehicles
        ORDER BY id DESC
    """)

    content = "<h2>Транспорт</h2>"
    content += "<p><a href='/vehicles/new'>➕ Добавить транспорт</a></p>"

    if rows:
        content += """
        <table border='1' cellpadding='8' cellspacing='0'
               style='border-collapse: collapse; width:100%; font-size:14px;'>
            <tr>
                <th>ID</th>
                <th>Наименование транспорта</th>
                <th>Гос.номер</th>
                <th>Тип учета</th>
                <th>Базовая норма</th>
                <th>Без груза</th>
                <th>С грузом</th>
                <th>Тяжелые условия</th>
                <th>Действия</th>
            </tr>
        """

        for row in rows:
            unit = meter_unit(row["meter_type"])
            base_text = f"{row['base_consumption']} {unit}" if row["base_consumption"] else ""

            content += f"""
            <tr>
                <td>{row['id']}</td>
                <td>{row['vehicle_name'] or ''}</td>
                <td>{row['plate_number'] or ''}</td>
                <td>{meter_type_label(row['meter_type'])}</td>
                <td>{base_text}</td>
                <td>{row['load_coeff_empty'] or ''}</td>
                <td>{row['load_coeff_loaded'] or ''}</td>
                <td>{row['load_coeff_heavy'] or ''}</td>
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
        vehicle_name = request.form.get("vehicle_name", "").strip()
        plate_number = request.form.get("plate_number", "").strip().upper()
        meter_type = request.form.get("meter_type") or None
        base_consumption = request.form.get("base_consumption") or None
        load_coeff_empty = request.form.get("load_coeff_empty") or 1.00
        load_coeff_loaded = request.form.get("load_coeff_loaded") or 1.15
        load_coeff_heavy = request.form.get("load_coeff_heavy") or 1.30

        execute_query("""
            INSERT INTO vehicles (
                vehicle_name,
                plate_number,
                meter_type,
                base_consumption,
                load_coeff_empty,
                load_coeff_loaded,
                load_coeff_heavy
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            vehicle_name,
            plate_number,
            meter_type,
            base_consumption,
            load_coeff_empty,
            load_coeff_loaded,
            load_coeff_heavy
        ))

        return redirect("/vehicles")

    content = """
    <div style='max-width:700px; margin:0 auto;'>
        <h2>Добавить транспорт</h2>

        <form method='post' style='display:flex; flex-direction:column; gap:12px;'>

            <div>
                <label>Наименование транспорта:</label><br>
                <input type='text' name='vehicle_name' required
                       style='width:100%; padding:8px;'>
            </div>

            <div>
                <label>Гос.номер:</label><br>
                <input type='text' name='plate_number' required
                       style='width:100%; padding:8px;'>
            </div>

            <div>
                <label>Тип учета:</label><br>
                <select name='meter_type' required style='width:100%; padding:8px;'>
                    <option value=''>-- Выберите --</option>
                    <option value='speedometer'>Спидометр</option>
                    <option value='motohours'>Моточасы</option>
                </select>
            </div>

            <div>
                <label>Базовая норма расхода:</label><br>
                <input type='number' step='0.01' name='base_consumption'
                       style='width:100%; padding:8px;'>
                <small>Для спидометра: л/100 км, для моточасов: л/моточас</small>
            </div>

            <div>
                <label>Коэффициент без груза:</label><br>
                <input type='number' step='0.01' name='load_coeff_empty' value='1.00'
                       style='width:100%; padding:8px;'>
            </div>

            <div>
                <label>Коэффициент с грузом:</label><br>
                <input type='number' step='0.01' name='load_coeff_loaded' value='1.15'
                       style='width:100%; padding:8px;'>
            </div>

            <div>
                <label>Коэффициент тяжелых условий:</label><br>
                <input type='number' step='0.01' name='load_coeff_heavy' value='1.30'
                       style='width:100%; padding:8px;'>
            </div>

            <div style='margin-top:8px;'>
                <button type='submit' style='padding:10px 16px;'>Сохранить</button>
                <a href='/vehicles' style='margin-left:12px;'>Отмена</a>
            </div>

        </form>
    </div>
    """

    return render_page("Добавить транспорт", content)


@vehicles_bp.route("/vehicles/edit/<int:vehicle_id>", methods=["GET", "POST"])
@login_required
def vehicles_edit(vehicle_id):
    vehicle = fetch_one("""
        SELECT
            id,
            vehicle_name,
            plate_number,
            meter_type,
            base_consumption,
            load_coeff_empty,
            load_coeff_loaded,
            load_coeff_heavy
        FROM vehicles
        WHERE id = %s
    """, (vehicle_id,))

    if not vehicle:
        return render_page("Ошибка", "<p>Транспорт не найден.</p>")

    if request.method == "POST":
        vehicle_name = request.form.get("vehicle_name", "").strip()
        plate_number = request.form.get("plate_number", "").strip().upper()
        meter_type = request.form.get("meter_type") or None
        base_consumption = request.form.get("base_consumption") or None
        load_coeff_empty = request.form.get("load_coeff_empty") or 1.00
        load_coeff_loaded = request.form.get("load_coeff_loaded") or 1.15
        load_coeff_heavy = request.form.get("load_coeff_heavy") or 1.30

        execute_query("""
            UPDATE vehicles
            SET
                vehicle_name = %s,
                plate_number = %s,
                meter_type = %s,
                base_consumption = %s,
                load_coeff_empty = %s,
                load_coeff_loaded = %s,
                load_coeff_heavy = %s
            WHERE id = %s
        """, (
            vehicle_name,
            plate_number,
            meter_type,
            base_consumption,
            load_coeff_empty,
            load_coeff_loaded,
            load_coeff_heavy,
            vehicle_id
        ))

        return redirect("/vehicles")

    speedometer_selected = "selected" if vehicle["meter_type"] == "speedometer" else ""
    motohours_selected = "selected" if vehicle["meter_type"] == "motohours" else ""

    content = f"""
    <div style='max-width:700px; margin:0 auto;'>
        <h2>Редактировать транспорт</h2>

        <form method='post' style='display:flex; flex-direction:column; gap:12px;'>

            <div>
                <label>Наименование транспорта:</label><br>
                <input type='text' name='vehicle_name' value='{vehicle['vehicle_name'] or ''}' required
                       style='width:100%; padding:8px;'>
            </div>

            <div>
                <label>Гос.номер:</label><br>
                <input type='text' name='plate_number' value='{vehicle['plate_number'] or ''}' required
                       style='width:100%; padding:8px;'>
            </div>

            <div>
                <label>Тип учета:</label><br>
                <select name='meter_type' required style='width:100%; padding:8px;'>
                    <option value=''>-- Выберите --</option>
                    <option value='speedometer' {speedometer_selected}>Спидометр</option>
                    <option value='motohours' {motohours_selected}>Моточасы</option>
                </select>
            </div>

            <div>
                <label>Базовая норма расхода:</label><br>
                <input type='number' step='0.01' name='base_consumption'
                       value='{vehicle['base_consumption'] or ""}'
                       style='width:100%; padding:8px;'>
                <small>Для спидометра: л/100 км, для моточасов: л/моточас</small>
            </div>

            <div>
                <label>Коэффициент без груза:</label><br>
                <input type='number' step='0.01' name='load_coeff_empty'
                       value='{vehicle['load_coeff_empty'] or 1.00}'
                       style='width:100%; padding:8px;'>
            </div>

            <div>
                <label>Коэффициент с грузом:</label><br>
                <input type='number' step='0.01' name='load_coeff_loaded'
                       value='{vehicle['load_coeff_loaded'] or 1.15}'
                       style='width:100%; padding:8px;'>
            </div>

            <div>
                <label>Коэффициент тяжелых условий:</label><br>
                <input type='number' step='0.01' name='load_coeff_heavy'
                       value='{vehicle['load_coeff_heavy'] or 1.30}'
                       style='width:100%; padding:8px;'>
            </div>

            <div style='margin-top:8px;'>
                <button type='submit' style='padding:10px 16px;'>Сохранить</button>
                <a href='/vehicles' style='margin-left:12px;'>Назад</a>
            </div>

        </form>
    </div>
    """

    return render_page("Редактировать транспорт", content)
