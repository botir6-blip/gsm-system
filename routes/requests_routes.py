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
            o.name AS object_name,
            v.plate_number,
            v.vehicle_name,
            r.requested_liters,
            r.actual_liters,
            r.requested_by,
            r.approved_by,
            r.fueler_name,
            r.controller_name,
            r.status,
            r.created_at,
            r.approved_at,
            r.fueled_at,
            r.checked_at
        FROM fuel_requests r
        LEFT JOIN objects o ON o.id = r.object_id
        LEFT JOIN vehicles v ON v.id = r.vehicle_id
        ORDER BY r.id DESC
    """)

    def status_label(status):
        if status == "new":
            return "Новая заявка"
        if status == "approved":
            return "Разрешена"
        if status == "fueled":
            return "Заправлена"
        if status == "driver_confirmed":
            return "Подтверждена водителем"
        if status == "checked":
            return "Проверена"
        return status or ""

    content = "<h2>Заявки</h2>"
    content += "<p><a href='/requests/new'>➕ Новая заявка</a></p>"

    if rows:
        for r in rows:
            content += f"""
            <div style='border:1px solid #ddd; border-radius:10px; padding:12px; margin-bottom:12px; background:#fff;'>
                <div style='display:flex; justify-content:space-between; gap:10px; flex-wrap:wrap;'>
                    <div><b>Заявка №{r['id']}</b></div>
                    <div><b>Статус:</b> {status_label(r['status'])}</div>
                </div>

                <div style='margin-top:8px; font-size:14px;'>
                    <div><b>Объект:</b> {r['object_name'] or ''}</div>
                    <div><b>Транспорт:</b> {(r['plate_number'] or '')} {(r['vehicle_name'] or '')}</div>
                    <div><b>Запрошено:</b> {r['requested_liters'] or ''} л</div>
                    <div><b>Фактически:</b> {r['actual_liters'] or ''} л</div>
                </div>

                <div style='margin-top:10px; padding:10px; background:#f8f8f8; border-radius:8px; font-size:14px;'>
                    <div><b>1. Заявку подал:</b> {r['requested_by'] or '—'}</div>
                    <div><b>2. Разрешил:</b> {r['approved_by'] or '—'}</div>
                    <div><b>3. Заправил:</b> {r['fueler_name'] or '—'}</div>
                    <div><b>4. Подтверждение водителя:</b> —</div>
                    <div><b>5. Проверил:</b> {r['controller_name'] or '—'}</div>
                </div>

                <div style='margin-top:10px; font-size:13px; color:#555;'>
                    <div><b>Создана:</b> {r['created_at'] or '—'}</div>
                    <div><b>Разрешена:</b> {r['approved_at'] or '—'}</div>
                    <div><b>Заправлена:</b> {r['fueled_at'] or '—'}</div>
                    <div><b>Проверена:</b> {r['checked_at'] or '—'}</div>
                </div>
            </div>
            """
    else:
        content += "<p>Заявок пока нет.</p>"

    return render_page("Заявки", content)


@requests_bp.route("/requests/new", methods=["GET", "POST"])
@login_required
def new_request():
    import json

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
        {"id": o["id"], "label": o["name"] or ""}
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

            <div style='position:relative;'>
                <label><b>1. Объект заправки:</b></label><br>
                <input
                    type='text'
                    id='object_search'
                    placeholder='Начните вводить название объекта'
                    autocomplete='off'
                    style='width:100%; padding:8px;'
                    required
                >
                <input type='hidden' name='object_id' id='object_id' required>
                <div id='object_results' style='display:none; position:absolute; left:0; right:0; background:#fff; border:1px solid #ccc; max-height:180px; overflow-y:auto; z-index:1000;'></div>
            </div>

            <div style='position:relative;'>
                <label><b>2. Транспорт:</b></label><br>
                <input
                    type='text'
                    id='vehicle_search'
                    placeholder='Начните вводить гос.номер, транспорт или тип'
                    autocomplete='off'
                    style='width:100%; padding:8px;'
                    required
                >
                <input type='hidden' name='vehicle_id' id='vehicle_id' required>
                <div id='vehicle_results' style='display:none; position:absolute; left:0; right:0; background:#fff; border:1px solid #ccc; max-height:220px; overflow-y:auto; z-index:1000;'></div>
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

    content += f"""
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
        const objectResults = document.getElementById('object_results');

        const vehicleSearch = document.getElementById('vehicle_search');
        const vehicleId = document.getElementById('vehicle_id');
        const vehicleResults = document.getElementById('vehicle_results');

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

        function renderResults(container, items, onPick) {{
            if (!items.length) {{
                container.style.display = 'none';
                container.innerHTML = '';
                return;
            }}

            container.innerHTML = items.map(item =>
                `<div style="padding:8px; cursor:pointer; border-bottom:1px solid #eee;" data-id="${{item.id}}">${{item.label}}</div>`
            ).join('');

            container.style.display = 'block';

            Array.from(container.children).forEach((el, index) => {{
                el.addEventListener('click', () => onPick(items[index]));
            }});
        }}

        objectSearch.addEventListener('input', function() {{
            const q = this.value.trim().toLowerCase();
            objectId.value = '';

            if (!q) {{
                objectResults.style.display = 'none';
                objectResults.innerHTML = '';
                return;
            }}

            const filtered = objectsData
                .filter(item => item.label.toLowerCase().includes(q))
                .slice(0, 20);

            renderResults(objectResults, filtered, (item) => {{
                objectSearch.value = item.label;
                objectId.value = item.id;
                objectResults.style.display = 'none';
            }});
        }});

        vehicleSearch.addEventListener('input', function() {{
            const q = this.value.trim().toLowerCase();
            vehicleId.value = '';
            clearVehicleInfo();

            if (!q) {{
                vehicleResults.style.display = 'none';
                vehicleResults.innerHTML = '';
                return;
            }}

            const filtered = vehiclesData
                .filter(item => item.label.toLowerCase().includes(q))
                .slice(0, 20);

            renderResults(vehicleResults, filtered, (item) => {{
                vehicleSearch.value = item.label;
                vehicleId.value = item.id;
                vehicleResults.style.display = 'none';

                document.getElementById('info_vehicle_type').textContent = item.vehicle_type || '—';
                document.getElementById('info_meter_type').textContent = meterTypeLabel(item.meter_type);
                document.getElementById('info_base_consumption').textContent =
                    item.base_consumption ? (item.base_consumption + ' ' + meterUnit(item.meter_type)) : '—';
                document.getElementById('info_empty').textContent = item.load_coeff_empty || '—';
                document.getElementById('info_loaded').textContent = item.load_coeff_loaded || '—';
                document.getElementById('info_heavy').textContent = item.load_coeff_heavy || '—';
            }});
        }});

        document.addEventListener('click', function(e) {{
            if (!objectSearch.parentNode.contains(e.target)) {{
                objectResults.style.display = 'none';
            }}
            if (!vehicleSearch.parentNode.contains(e.target)) {{
                vehicleResults.style.display = 'none';
            }}
        }});
    </script>
    """

    return render_page("Новая заявка", content)
