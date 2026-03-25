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
    if value == "both":
        return "Спидометр + Моточасы"
    return ""


def meter_unit(value):
    if value == "speedometer":
        return "л/100 км"
    if value == "motohours":
        return "л/моточас"
    return ""


def has_dual_meter_columns():
    rows = fetch_all("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'vehicles'
          AND column_name IN (
              'has_speedometer',
              'has_motohours',
              'base_consumption_speedometer',
              'base_consumption_motohours'
          )
    """)
    found = {row["column_name"] for row in rows}
    required = {
        "has_speedometer",
        "has_motohours",
        "base_consumption_speedometer",
        "base_consumption_motohours"
    }
    return required.issubset(found)


def build_meter_display(row, dual_mode):
    if dual_mode:
        parts = []

        if row.get("has_speedometer"):
            norm = row.get("base_consumption_speedometer")
            if norm not in (None, ""):
                parts.append(f"Спидометр ({norm} л/100 км)")
            else:
                parts.append("Спидометр")

        if row.get("has_motohours"):
            norm = row.get("base_consumption_motohours")
            if norm not in (None, ""):
                parts.append(f"Моточасы ({norm} л/моточас)")
            else:
                parts.append("Моточасы")

        return "<br>".join(parts)

    unit = meter_unit(row.get("meter_type"))
    if row.get("base_consumption"):
        return f"{meter_type_label(row.get('meter_type'))}<br>{row['base_consumption']} {unit}"
    return meter_type_label(row.get("meter_type"))


@vehicles_bp.route("/vehicles")
@login_required
def vehicles_page():
    dual_mode = has_dual_meter_columns()

    if dual_mode:
        rows = fetch_all("""
            SELECT
                id,
                vehicle_name,
                vehicle_type,
                plate_number,
                has_speedometer,
                has_motohours,
                base_consumption_speedometer,
                base_consumption_motohours,
                load_coeff_empty,
                load_coeff_loaded,
                load_coeff_heavy
            FROM vehicles
            ORDER BY id DESC
        """)
    else:
        rows = fetch_all("""
            SELECT
                id,
                vehicle_name,
                vehicle_type,
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
                <th>Тип транспорта</th>
                <th>Гос.номер</th>
                <th>Тип учета / норма</th>
                <th>Без груза</th>
                <th>С грузом</th>
                <th>Тяжелые условия</th>
                <th>Действия</th>
            </tr>
        """

        for row in rows:
            meter_text = build_meter_display(row, dual_mode)

            content += f"""
            <tr>
                <td>{row['id']}</td>
                <td>{row['vehicle_name'] or ''}</td>
                <td>{row['vehicle_type'] or ''}</td>
                <td>{row['plate_number'] or ''}</td>
                <td>{meter_text}</td>
                <td>{row['load_coeff_empty'] or ''}</td>
                <td>{row['load_coeff_loaded'] or ''}</td>
                <td>{row['load_coeff_heavy'] or ''}</td>
                <td style="white-space:nowrap;">
                    <a href='/vehicles/edit/{row["id"]}'>✏️ Редактировать</a>
                    &nbsp;|&nbsp;
                    <form method="POST"
                          action="/vehicles/delete/{row['id']}"
                          style="display:inline;"
                          onsubmit="return confirm('Удалить транспорт?')">
                        <button type="submit"
                                style="background:none;border:none;color:#c62828;cursor:pointer;padding:0;">
                            🗑 Удалить
                        </button>
                    </form>
                </td>
            </tr>
            """

        content += "</table>"
    else:
        content += "<p>Транспорт пока не добавлен.</p>"

    return render_page("Транспорт", content)


@vehicles_bp.route("/vehicles/new", methods=["GET", "POST"])
@login_required
def vehicles_new():
    dual_mode = has_dual_meter_columns()

    if request.method == "POST":
        vehicle_name = request.form.get("vehicle_name", "").strip()
        vehicle_type = request.form.get("vehicle_type", "").strip()
        plate_number = request.form.get("plate_number", "").strip().upper()

        load_coeff_empty = request.form.get("load_coeff_empty") or 1.00
        load_coeff_loaded = request.form.get("load_coeff_loaded") or 1.15
        load_coeff_heavy = request.form.get("load_coeff_heavy") or 1.30

        if dual_mode:
            has_speedometer = True if request.form.get("has_speedometer") else False
            has_motohours = True if request.form.get("has_motohours") else False

            base_consumption_speedometer = request.form.get("base_consumption_speedometer") or None
            base_consumption_motohours = request.form.get("base_consumption_motohours") or None

            execute_query("""
                INSERT INTO vehicles (
                    vehicle_name,
                    vehicle_type,
                    plate_number,
                    has_speedometer,
                    has_motohours,
                    base_consumption_speedometer,
                    base_consumption_motohours,
                    load_coeff_empty,
                    load_coeff_loaded,
                    load_coeff_heavy
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                vehicle_name,
                vehicle_type,
                plate_number,
                has_speedometer,
                has_motohours,
                base_consumption_speedometer,
                base_consumption_motohours,
                load_coeff_empty,
                load_coeff_loaded,
                load_coeff_heavy
            ))
        else:
            meter_type = request.form.get("meter_type") or None
            base_consumption = request.form.get("base_consumption") or None

            execute_query("""
                INSERT INTO vehicles (
                    vehicle_name,
                    vehicle_type,
                    plate_number,
                    meter_type,
                    base_consumption,
                    load_coeff_empty,
                    load_coeff_loaded,
                    load_coeff_heavy
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                vehicle_name,
                vehicle_type,
                plate_number,
                meter_type,
                base_consumption,
                load_coeff_empty,
                load_coeff_loaded,
                load_coeff_heavy
            ))

        return redirect("/vehicles")

    if dual_mode:
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
                    <label>Тип транспорта:</label><br>
                    <input type='text' name='vehicle_type'
                           style='width:100%; padding:8px;'>
                </div>

                <div>
                    <label>Гос.номер:</label><br>
                    <input type='text' name='plate_number' required
                           style='width:100%; padding:8px;'>
                </div>

                <div>
                    <label style='display:block; margin-bottom:6px;'>Тип учета:</label>
                    <label style='display:block; margin-bottom:6px;'>
                        <input type='checkbox' name='has_speedometer' value='1'> Спидометр
                    </label>
                    <label style='display:block;'>
                        <input type='checkbox' name='has_motohours' value='1'> Моточасы
                    </label>
                </div>

                <div>
                    <label>Базовая норма расхода (спидометр, л/100 км):</label><br>
                    <input type='number' step='0.01' name='base_consumption_speedometer'
                           style='width:100%; padding:8px;'>
                </div>

                <div>
                    <label>Базовая норма расхода (моточасы, л/моточас):</label><br>
                    <input type='number' step='0.01' name='base_consumption_motohours'
                           style='width:100%; padding:8px;'>
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
    else:
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
                    <label>Тип транспорта:</label><br>
                    <input type='text' name='vehicle_type'
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
                        <option value='both'>Спидометр + Моточасы</option>
                    </select>
                </div>

                <div>
                    <label>Базовая норма расхода:</label><br>
                    <input type='number' step='0.01' name='base_consumption'
                           style='width:100%; padding:8px;'>
                    <small>Пока старая версия базы: одна общая норма</small>
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
    dual_mode = has_dual_meter_columns()

    if dual_mode:
        vehicle = fetch_one("""
            SELECT
                id,
                vehicle_name,
                vehicle_type,
                plate_number,
                has_speedometer,
                has_motohours,
                base_consumption_speedometer,
                base_consumption_motohours,
                load_coeff_empty,
                load_coeff_loaded,
                load_coeff_heavy
            FROM vehicles
            WHERE id = %s
        """, (vehicle_id,))
    else:
        vehicle = fetch_one("""
            SELECT
                id,
                vehicle_name,
                vehicle_type,
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
        vehicle_type = request.form.get("vehicle_type", "").strip()
        plate_number = request.form.get("plate_number", "").strip().upper()

        load_coeff_empty = request.form.get("load_coeff_empty") or 1.00
        load_coeff_loaded = request.form.get("load_coeff_loaded") or 1.15
        load_coeff_heavy = request.form.get("load_coeff_heavy") or 1.30

        if dual_mode:
            has_speedometer = True if request.form.get("has_speedometer") else False
            has_motohours = True if request.form.get("has_motohours") else False

            base_consumption_speedometer = request.form.get("base_consumption_speedometer") or None
            base_consumption_motohours = request.form.get("base_consumption_motohours") or None

            execute_query("""
                UPDATE vehicles
                SET
                    vehicle_name = %s,
                    vehicle_type = %s,
                    plate_number = %s,
                    has_speedometer = %s,
                    has_motohours = %s,
                    base_consumption_speedometer = %s,
                    base_consumption_motohours = %s,
                    load_coeff_empty = %s,
                    load_coeff_loaded = %s,
                    load_coeff_heavy = %s
                WHERE id = %s
            """, (
                vehicle_name,
                vehicle_type,
                plate_number,
                has_speedometer,
                has_motohours,
                base_consumption_speedometer,
                base_consumption_motohours,
                load_coeff_empty,
                load_coeff_loaded,
                load_coeff_heavy,
                vehicle_id
            ))
        else:
            meter_type = request.form.get("meter_type") or None
            base_consumption = request.form.get("base_consumption") or None

            execute_query("""
                UPDATE vehicles
                SET
                    vehicle_name = %s,
                    vehicle_type = %s,
                    plate_number = %s,
                    meter_type = %s,
                    base_consumption = %s,
                    load_coeff_empty = %s,
                    load_coeff_loaded = %s,
                    load_coeff_heavy = %s
                WHERE id = %s
            """, (
                vehicle_name,
                vehicle_type,
                plate_number,
                meter_type,
                base_consumption,
                load_coeff_empty,
                load_coeff_loaded,
                load_coeff_heavy,
                vehicle_id
            ))

        return redirect("/vehicles")

    if dual_mode:
        speedometer_checked = "checked" if vehicle["has_speedometer"] else ""
        motohours_checked = "checked" if vehicle["has_motohours"] else ""

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
                    <label>Тип транспорта:</label><br>
                    <input type='text' name='vehicle_type' value='{vehicle['vehicle_type'] or ''}'
                           style='width:100%; padding:8px;'>
                </div>

                <div>
                    <label>Гос.номер:</label><br>
                    <input type='text' name='plate_number' value='{vehicle['plate_number'] or ''}' required
                           style='width:100%; padding:8px;'>
                </div>

                <div>
                    <label style='display:block; margin-bottom:6px;'>Тип учета:</label>
                    <label style='display:block; margin-bottom:6px;'>
                        <input type='checkbox' name='has_speedometer' value='1' {speedometer_checked}> Спидометр
                    </label>
                    <label style='display:block;'>
                        <input type='checkbox' name='has_motohours' value='1' {motohours_checked}> Моточасы
                    </label>
                </div>

                <div>
                    <label>Базовая норма расхода (спидометр, л/100 км):</label><br>
                    <input type='number' step='0.01' name='base_consumption_speedometer'
                           value='{vehicle["base_consumption_speedometer"] or ""}'
                           style='width:100%; padding:8px;'>
                </div>

                <div>
                    <label>Базовая норма расхода (моточасы, л/моточас):</label><br>
                    <input type='number' step='0.01' name='base_consumption_motohours'
                           value='{vehicle["base_consumption_motohours"] or ""}'
                           style='width:100%; padding:8px;'>
                </div>

                <div>
                    <label>Коэффициент без груза:</label><br>
                    <input type='number' step='0.01' name='load_coeff_empty'
                           value='{vehicle["load_coeff_empty"] or 1.00}'
                           style='width:100%; padding:8px;'>
                </div>

                <div>
                    <label>Коэффициент с грузом:</label><br>
                    <input type='number' step='0.01' name='load_coeff_loaded'
                           value='{vehicle["load_coeff_loaded"] or 1.15}'
                           style='width:100%; padding:8px;'>
                </div>

                <div>
                    <label>Коэффициент тяжелых условий:</label><br>
                    <input type='number' step='0.01' name='load_coeff_heavy'
                           value='{vehicle["load_coeff_heavy"] or 1.30}'
                           style='width:100%; padding:8px;'>
                </div>

                <div style='margin-top:8px;'>
                    <button type='submit' style='padding:10px 16px;'>Сохранить</button>
                    <a href='/vehicles' style='margin-left:12px;'>Назад</a>
                </div>

            </form>
        </div>
        """
    else:
        speedometer_selected = "selected" if vehicle["meter_type"] == "speedometer" else ""
        motohours_selected = "selected" if vehicle["meter_type"] == "motohours" else ""
        both_selected = "selected" if vehicle["meter_type"] == "both" else ""

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
                    <label>Тип транспорта:</label><br>
                    <input type='text' name='vehicle_type' value='{vehicle['vehicle_type'] or ''}'
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
                        <option value='both' {both_selected}>Спидометр + Моточасы</option>
                    </select>
                </div>

                <div>
                    <label>Базовая норма расхода:</label><br>
                    <input type='number' step='0.01' name='base_consumption'
                           value='{vehicle['base_consumption'] or ""}'
                           style='width:100%; padding:8px;'>
                    <small>Пока старая версия базы: одна общая норма</small>
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


@vehicles_bp.route("/vehicles/delete/<int:vehicle_id>", methods=["POST"])
@login_required
def delete_vehicle(vehicle_id):
    vehicle = fetch_one("SELECT id FROM vehicles WHERE id = %s", (vehicle_id,))

    if vehicle:
        execute_query("DELETE FROM vehicles WHERE id = %s", (vehicle_id,))

    return redirect("/vehicles")
