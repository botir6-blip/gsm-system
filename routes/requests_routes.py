from flask import Blueprint, request, redirect
from auth import login_required
from layout import render_page
from db import fetch_all, execute_query
import json

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
        ORDER BY plate_number
    """)

    users = fetch_all("""
        SELECT id, full_name
        FROM users
        ORDER BY full_name
    """)

    objects_js = json.dumps([
        {
            "id": o["id"],
            "label": o["name"] or ""
        }
        for o in objects
    ], ensure_ascii=False)

    vehicles_js = json.dumps([
        {
            "id": v["id"],
            "label": f"{v['plate_number'] or ''} | {v['vehicle_name'] or ''} | {v['vehicle_type'] or ''}",
            "vehicle_name": v["vehicle_name"] or "",
            "vehicle_type": v["vehicle_type"] or "",
            "plate_number": v["plate_number"] or "",
            "meter_type": v["meter_type"] or "",
            "base_consumption": str(v["base_consumption"] or ""),
            "load_coeff_empty": str(v["load_coeff_empty"] or ""),
            "load_coeff_loaded": str(v["load_coeff_loaded"] or ""),
            "load_coeff_heavy": str(v["load_coeff_heavy"] or "")
        }
        for v in vehicles
    ], ensure_ascii=False)

    content = f"""
    <div style='max-width:760px; margin:0 auto;'>
        <h2 style='margin-bottom:16px;'>Новая заявка</h2>

        <form method='post' style='display:flex; flex-direction:column; gap:12px;'>

            <div>
                <label><b>1. Объект заправки:</b></label><br>
                <input
                    type='text'
                    id='object_search'
                    list='objects_list'
                    placeholder='Начните вводить название объекта'
                    autocomplete='off'
                    style='width:100%; padding:8px;'
                    required
                >
                <datalist id='objects_list'></datalist>
                <input type='hidden' name='object_id' id='object_id' required>
            </div>

            <div>
                <label><b>2. Транспорт:</b></label><br>
                <input
                    type='text'
                    id='vehicle_search'
                    list='vehicles_list'
                    placeholder='Начните вводить гос.номер, наименование или тип'
                    autocomplete='off'
                    style='width:100%; padding:8px;'
                    required
                >
                <datalist id='vehicles_list'></datalist>
                <input type='hidden' name='vehicle_id' id='vehicle_id' required>
            </div>

            <div id='vehicle_info' style='padding:10px; border:1px solid #ddd; border-radius:8px; background:#f9f9f9; font-size:14px;'>
                <div><b>Тип транспорта:</b> <span id='info_vehicle_type'>—</span></div>
                <div><b>Тип учета:</b> <span id='info_meter_type'>—</span></div>
                <div><b>Базовая норма:</b> <span id='info_base_consumption'>—</span></div>
                <div><b>Коэффициент без груза:</b> <span id='info_empty'>—</span></div>
                <div><b>Коэффициент с грузом:</b> <span id='info_loaded'>—</span></div>
                <div><b>Коэффициент тяжелых условий:</b> <span id='info_heavy'>—</span></div>
            </div>

            <div>
                <label><b>3. Остаток в баке (л):</b></label><br>
                <input type='number' step='0.01' name='tank_balance' style='width:100%; padding:8px;'>
            </div>

            <div>
                <label><b>4. Запрашиваемое количество топлива (л):</b></label><br>
                <input type='number' step='0.01' name='requested_liters' required style='width:100%; padding:8px;'>
            </div>

            <div>
                <label><b>5. Маршрут / объем работ:</b></label><br>
                <input type='text' name='route_work' style='width:100%; padding:8px;'>
            </div>

            <div>
                <label><b>6. Кто подает заявку:</b></label><br>
                <select name='requested_by' required style='width:100%; padding:8px;'>
                    <option value=''>-- Выберите --</option>
    """

    for u in users:
        content += f"<option value='{u['full_name']}'>{u['full_name']}</option>"

    content += """
                </select>
            </div>

            <div>
                <label><b>7. Проект:</b></label><br>
                <input type='text' name='project_name' style='width:100%; padding:8px;'>
            </div>

            <div>
                <label><b>8. Комментарий:</b></label><br>
                <textarea name='comment' rows='4' style='width:100%; padding:8px;'></textarea>
            </div>

            <div style='margin-top:8px;'>
                <button type='submit' style='padding:10px 16px;'>Сохранить заявку</button>
                <a href='/requests' style='margin-left:12px;'>Назад</a>
            </div>

        </form>
    </div>

    <script>
        const objectsData = {objects_js};
        const vehiclesData = {vehicles_js};

        const objectSearch = document.getElementById('object_search');
        const objectId = document.getElementById('object_id');
        const objectsList = document.getElementById('objects_list');

        const vehicleSearch = document.getElementById('vehicle_search');
        const vehicleId = document.getElementById('vehicle_id');
        const vehiclesList = document.getElementById('vehicles_list');

        function fillDatalist(listEl, data) {{
            listEl.innerHTML = '';
            data.forEach(item => {{
                const option = document.createElement('option');
                option.value = item.label;
                listEl.appendChild(option);
            }});
        }}

        fillDatalist(objectsList, objectsData);
        fillDatalist(vehiclesList, vehiclesData);

        objectSearch.addEventListener('input', function() {{
            const found = objectsData.find(item => item.label === this.value);
            objectId.value = found ? found.id : '';
        }});

        function meterTypeLabel(value) {{
            if (value === 'speedometer') return 'Спидометр';
            if (value === 'motohours') return 'Моточасы';
            return '—';
        }}

        function meterUnit(value) {{
            if (value === 'speedometer') return 'л/100 км';
            if (value === 'motohours') return 'л/моточас';
            return '';
        }}

        function clearVehicleInfo() {{
            document.getElementById('info_vehicle_type').textContent = '—';
            document.getElementById('info_meter_type').textContent = '—';
            document.getElementById('info_base_consumption').textContent = '—';
            document.getElementById('info_empty').textContent = '—';
            document.getElementById('info_loaded').textContent = '—';
            document.getElementById('info_heavy').textContent = '—';
        }}

        vehicleSearch.addEventListener('input', function() {{
            const found = vehiclesData.find(item => item.label === this.value);
            vehicleId.value = found ? found.id : '';

            if (!found) {{
                clearVehicleInfo();
                return;
            }}

            document.getElementById('info_vehicle_type').textContent = found.vehicle_type || '—';
            document.getElementById('info_meter_type').textContent = meterTypeLabel(found.meter_type);
            document.getElementById('info_base_consumption').textContent =
                found.base_consumption ? (found.base_consumption + ' ' + meterUnit(found.meter_type)) : '—';
            document.getElementById('info_empty').textContent = found.load_coeff_empty || '—';
            document.getElementById('info_loaded').textContent = found.load_coeff_loaded || '—';
            document.getElementById('info_heavy').textContent = found.load_coeff_heavy || '—';
        }});
    </script>
    """

    return render_page("Новая заявка", content)
