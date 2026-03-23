import json
from flask import Blueprint, request, redirect, session
from auth import login_required
from layout import render_page
from db import fetch_all, fetch_one, execute_query

requests_bp = Blueprint("requests_bp", __name__)


def current_user_name():
    return (
        session.get("full_name")
        or session.get("username")
        or session.get("login")
        or session.get("user_name")
        or "Пользователь"
    )


def status_label(status):
    if status == "new":
        return "Новая"
    if status == "approved":
        return "Разрешена"
    if status == "fueled":
        return "Заправлена"
    if status == "driver_confirmed":
        return "Подтверждена водителем"
    if status == "checked":
        return "Закрыта"
    if status == "rejected":
        return "Отклонена"
    return status or "—"


def status_color(status):
    if status == "checked":
        return "#2e7d32"
    if status == "approved":
        return "#1565c0"
    if status == "fueled":
        return "#ef6c00"
    if status == "driver_confirmed":
        return "#6a1b9a"
    if status == "rejected":
        return "#c62828"
    return "#8d6e63"


def meter_type_label(value):
    if value == "speedometer":
        return "Спидометр"
    if value == "motohours":
        return "Моточасы"
    return "—"


def meter_unit(value):
    if value == "speedometer":
        return "л/100 км"
    if value == "motohours":
        return "л/моточас"
    return ""


@requests_bp.route("/requests")
@login_required
def requests_page():
    user_role = session.get("role", "")
    can_create_request = user_role in ["admin", "dispatcher", "operator", "master"]

    rows = fetch_all("""
        SELECT
            r.id,
            o.name AS object_name,
            v.plate_number,
            v.vehicle_name,
            v.vehicle_type,
            v.meter_type,
            v.base_consumption,
            v.load_coeff_empty,
            v.load_coeff_loaded,
            v.load_coeff_heavy,
            r.requested_liters,
            r.actual_liters,
            r.requested_by,
            r.approved_by,
            r.fueler_name,
            r.controller_name,
            r.status,
            r.created_at,
            r.project_name,
            r.fuel_supplier
        FROM fuel_requests r
        LEFT JOIN objects o ON o.id = r.object_id
        LEFT JOIN vehicles v ON v.id = r.vehicle_id
        ORDER BY
            CASE WHEN r.status = 'checked' THEN 1 ELSE 0 END,
            r.id DESC
    """)

    content = """
    <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; gap:10px;'>
        <h2 style='margin:0;'>Заявки</h2>
    """

    if can_create_request:
        content += """
        <a href='/requests/new' style='text-decoration:none; padding:8px 12px; border:1px solid #ccc; border-radius:8px;'>
            ➕ Новая заявка
        </a>
        """

    content += "</div>"

    if rows:
        content += """
        <div style='overflow-x:auto;'>
        <table border='1' cellpadding='8' cellspacing='0'
               style='border-collapse:collapse; width:100%; font-size:14px; background:#fff;'>
            <tr style='background:#f5f5f5;'>
                <th>ID</th>
                <th>Статус</th>
                <th>Объект</th>
                <th>Транспорт</th>
                <th>Норма</th>
                <th>Запрос</th>
                <th>За чей счет</th>
                <th>Подал</th>
                <th>Действия</th>
            </tr>
        """

        for r in rows:
            transport = f"{r['plate_number'] or ''} {r['vehicle_name'] or ''}".strip()
            fact_text = f" / факт {r['actual_liters']} л" if r["actual_liters"] else ""
            norm_text = ""
            if r["base_consumption"]:
                norm_text = f"{r['base_consumption']} {meter_unit(r['meter_type'])}"

            approve_btn = ""
            if r["status"] == "new":
                approve_btn = f"""
                    <a href='/requests/{r["id"]}' style='margin-left:8px;'>Согласовать</a>
                """

            row_bg = "background:#e8f5e9;" if r["status"] == "checked" else ""

            content += f"""
            <tr style='{row_bg}'>
                <td>{r['id']}</td>
                <td>
                    <span style='display:inline-block; padding:3px 8px; border-radius:999px; color:#fff; background:{status_color(r["status"])};'>
                        {status_label(r['status'])}
                    </span>
                </td>
                <td>{r['object_name'] or '—'}</td>
                <td>{transport or '—'}</td>
                <td>{norm_text or '—'}</td>
                <td>{r['requested_liters'] or '—'} л{fact_text}</td>
                <td>{r['fuel_supplier'] or '—'}</td>
                <td>{r['requested_by'] or '—'}</td>
                <td style='white-space:nowrap;'>
                    <a href='/requests/{r["id"]}'>Подробнее</a>
                    {approve_btn}
                </td>
            </tr>
            """

        content += "</table></div>"
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
        fuel_supplier = request.form.get("fuel_supplier") or ""
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
                fuel_supplier,
                request_comment,
                status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'new')
        """, (
            object_id,
            vehicle_id,
            requested_liters,
            requested_by,
            project_name,
            fuel_supplier,
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

    companies = fetch_all("""
        SELECT id, name
        FROM companies
        ORDER BY name
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

    content += """
                </select>
            </div>

            <div>
                <label><b>7. Проект:</b></label><br>
                <input type='text' name='project_name' style='width:100%; padding:8px;'>
            </div>

            <div>
                <label><b>8. За чей счет топливо:</b></label><br>
                <select name='fuel_supplier' style='width:100%; padding:8px;'>
                    <option value=''>-- Выберите --</option>
    """

    for c in companies:
        content += f"<option value='{c['name']}'>{c['name']}</option>"

    content += """
                </select>
            </div>

            <div>
                <label><b>9. Комментарий:</b></label><br>
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


@requests_bp.route("/requests/<int:request_id>")
@login_required
def request_detail(request_id):
    r = fetch_one("""
        SELECT
            r.*,
            o.name AS object_name,
            v.plate_number,
            v.vehicle_name,
            v.vehicle_type,
            v.meter_type,
            v.base_consumption,
            v.load_coeff_empty,
            v.load_coeff_loaded,
            v.load_coeff_heavy
        FROM fuel_requests r
        LEFT JOIN objects o ON o.id = r.object_id
        LEFT JOIN vehicles v ON v.id = r.vehicle_id
        WHERE r.id = %s
    """, (request_id,))

    if not r:
        return render_page("Ошибка", "<p>Заявка не найдена.</p>")

    transport = f"{r['plate_number'] or ''} {r['vehicle_name'] or ''}".strip()
    base_norm = "—"
    if r["base_consumption"]:
        base_norm = f"{r['base_consumption']} {meter_unit(r['meter_type'])}"

    content = f"""
    <div style='max-width:820px; margin:0 auto;'>
        <div style='display:flex; justify-content:space-between; align-items:center; gap:10px; margin-bottom:14px;'>
            <h2 style='margin:0;'>Заявка №{r['id']}</h2>
            <a href='/requests'>← Назад к списку</a>
        </div>

        <div style='border:1px solid #ddd; border-radius:10px; padding:14px; background:#fff;'>
            <div style='margin-bottom:10px;'>
                <span style='display:inline-block; padding:5px 10px; border-radius:999px; color:#fff; background:{status_color(r["status"])};'>
                    {status_label(r['status'])}
                </span>
            </div>

            <table style='width:100%; border-collapse:collapse; font-size:14px;'>
                <tr><td style='padding:6px; width:260px;'><b>Объект заправки</b></td><td style='padding:6px;'>{r['object_name'] or '—'}</td></tr>
                <tr><td style='padding:6px;'><b>Транспорт</b></td><td style='padding:6px;'>{transport or '—'}</td></tr>
                <tr><td style='padding:6px;'><b>Тип транспорта</b></td><td style='padding:6px;'>{r['vehicle_type'] or '—'}</td></tr>
                <tr><td style='padding:6px;'><b>Тип учета</b></td><td style='padding:6px;'>{meter_type_label(r['meter_type'])}</td></tr>
                <tr><td style='padding:6px;'><b>Базовая норма</b></td><td style='padding:6px;'>{base_norm}</td></tr>
                <tr><td style='padding:6px;'><b>Коэффициент без груза</b></td><td style='padding:6px;'>{r['load_coeff_empty'] or '—'}</td></tr>
                <tr><td style='padding:6px;'><b>Коэффициент с грузом</b></td><td style='padding:6px;'>{r['load_coeff_loaded'] or '—'}</td></tr>
                <tr><td style='padding:6px;'><b>Коэффициент тяжелых условий</b></td><td style='padding:6px;'>{r['load_coeff_heavy'] or '—'}</td></tr>
                <tr><td style='padding:6px;'><b>Запрошено топлива</b></td><td style='padding:6px;'>{r['requested_liters'] or '—'} л</td></tr>
                <tr><td style='padding:6px;'><b>Разрешено</b></td><td style='padding:6px;'>{r['approved_liters'] or '—'} л</td></tr>
                <tr><td style='padding:6px;'><b>Фактически отпущено</b></td><td style='padding:6px;'>{r['actual_liters'] or '—'} л</td></tr>
                <tr><td style='padding:6px;'><b>За чей счет топливо</b></td><td style='padding:6px;'>{r['fuel_supplier'] or '—'}</td></tr>
                <tr><td style='padding:6px;'><b>Проект</b></td><td style='padding:6px;'>{r['project_name'] or '—'}</td></tr>
                <tr><td style='padding:6px;'><b>Комментарий</b></td><td style='padding:6px;'>{r['request_comment'] or '—'}</td></tr>
            </table>
        </div>

        <div style='border:1px solid #ddd; border-radius:10px; padding:14px; background:#fff; margin-top:14px;'>
            <h3 style='margin-top:0;'>Ход согласования</h3>
            <table style='width:100%; border-collapse:collapse; font-size:14px;'>
                <tr><td style='padding:6px; width:260px;'><b>Заявку подал</b></td><td style='padding:6px;'>{r['requested_by'] or '—'}</td></tr>
                <tr><td style='padding:6px;'><b>Разрешил</b></td><td style='padding:6px;'>{r['approved_by'] or '—'}</td></tr>
                <tr><td style='padding:6px;'><b>Заправил</b></td><td style='padding:6px;'>{r['fueler_name'] or '—'}</td></tr>
                <tr><td style='padding:6px;'><b>Подтверждение водителя</b></td><td style='padding:6px;'>{"—" if "driver_name" not in r.keys() else (r["driver_name"] or "—")}</td></tr>
                <tr><td style='padding:6px;'><b>Проверил</b></td><td style='padding:6px;'>{r['controller_name'] or '—'}</td></tr>
            </table>
        </div>

        <div style='border:1px solid #ddd; border-radius:10px; padding:14px; background:#fff; margin-top:14px;'>
            <h3 style='margin-top:0;'>Даты</h3>
            <table style='width:100%; border-collapse:collapse; font-size:14px;'>
                <tr><td style='padding:6px; width:260px;'><b>Создана</b></td><td style='padding:6px;'>{r['created_at'] or '—'}</td></tr>
                <tr><td style='padding:6px;'><b>Разрешена</b></td><td style='padding:6px;'>{r['approved_at'] or '—'}</td></tr>
                <tr><td style='padding:6px;'><b>Заправлена</b></td><td style='padding:6px;'>{r['fueled_at'] or '—'}</td></tr>
                <tr><td style='padding:6px;'><b>Проверена</b></td><td style='padding:6px;'>{r['checked_at'] or '—'}</td></tr>
            </table>
        </div>
    """

    if r["status"] == "new":
        content += f"""
        <div style='border:1px solid #ddd; border-radius:10px; padding:14px; background:#fff; margin-top:14px;'>
            <h3 style='margin-top:0;'>Согласование</h3>

            <form method='post' action='/requests/{r["id"]}/decision'>
                <div style='margin-bottom:10px;'>
                    <label><b>Запрошено:</b></label><br>
                    <input type='text' value='{r["requested_liters"] or ""}' disabled
                           style='width:100%; padding:8px; background:#f5f5f5;'>
                </div>

                <div style='margin-bottom:10px;'>
                    <label><b>Одобрено литров:</b></label><br>
                    <input type='number' step='0.01' name='approved_liters'
                           value='{r["requested_liters"] or ""}'
                           style='width:100%; padding:8px;' required>
                </div>

                <div style='margin-bottom:10px;'>
                    <label><b>За чей счет топливо:</b></label><br>
                    <input type='text' name='fuel_supplier'
                           value='{r["fuel_supplier"] or ""}'
                           style='width:100%; padding:8px;'
                           required>
                </div>

                <div style='margin-bottom:10px;'>
                    <label><b>Тип согласования:</b></label><br>
                    <select name='approval_type' style='width:100%; padding:8px;'>
                        <option value='internal' {"selected" if r["approval_type"] == "internal" else ""}>Внутреннее</option>
                        <option value='external' {"selected" if r["approval_type"] == "external" else ""}>Внешнее</option>
                    </select>
                </div>

                <div style='margin-bottom:10px;'>
                    <label><b>Комментарий руководителя:</b></label><br>
                    <textarea name='approval_comment' rows='4'
                              style='width:100%; padding:8px;'></textarea>
                </div>

                <div style='display:flex; gap:8px; flex-wrap:wrap;'>
                    <button type='submit' name='decision' value='approve'
                            style='padding:10px 14px; border:none; border-radius:8px; background:#1565c0; color:white;'>
                        Разрешить
                    </button>

                    <button type='submit' name='decision' value='approve_adjusted'
                            style='padding:10px 14px; border:none; border-radius:8px; background:#ef6c00; color:white;'>
                        Разрешить с корректировкой
                    </button>

                    <button type='submit' name='decision' value='reject'
                            style='padding:10px 14px; border:none; border-radius:8px; background:#c62828; color:white;'>
                        Отклонить
                    </button>
                </div>
            </form>
        </div>
        """

    content += "</div>"

    return render_page(f"Заявка №{request_id}", content)


@requests_bp.route("/requests/<int:request_id>/decision", methods=["POST"])
@login_required
def request_decision(request_id):
    req = fetch_one("""
        SELECT id, status, requested_liters
        FROM fuel_requests
        WHERE id = %s
    """, (request_id,))

    if not req:
        return render_page("Ошибка", "<p>Заявка не найдена.</p>")

    if req["status"] != "new":
        return redirect(f"/requests/{request_id}")

    decision = request.form.get("decision")
    approved_liters = request.form.get("approved_liters") or req["requested_liters"]
    fuel_supplier = request.form.get("fuel_supplier") or ""
    approval_type = request.form.get("approval_type") or "internal"
    approval_comment = request.form.get("approval_comment") or ""
    approver = current_user_name()

    if decision == "reject":
        execute_query("""
            UPDATE fuel_requests
            SET
                status = 'rejected',
                rejected_by = %s,
                rejected_at = CURRENT_TIMESTAMP,
                approved_by = %s,
                approval_comment = %s,
                fuel_supplier = %s,
                approval_type = %s
            WHERE id = %s
        """, (
            approver,
            approver,
            approval_comment,
            fuel_supplier,
            approval_type,
            request_id
        ))
    else:
        execute_query("""
            UPDATE fuel_requests
            SET
                status = 'approved',
                approved_by = %s,
                approved_at = CURRENT_TIMESTAMP,
                approved_liters = %s,
                fuel_supplier = %s,
                approval_type = %s,
                approval_comment = %s
            WHERE id = %s
        """, (
            approver,
            approved_liters,
            fuel_supplier,
            approval_type,
            approval_comment,
            request_id
        ))

    return redirect(f"/requests/{request_id}")
