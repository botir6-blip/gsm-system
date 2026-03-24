from flask import Blueprint, request, redirect, session
from auth import login_required, current_user
from layout import render_page
from db import fetch_all, fetch_one, execute_query

requests_bp = Blueprint("requests_bp", __name__)


def current_user_name():
    user = current_user()
    if user:
        return (
            user.get("full_name")
            or user.get("username")
            or user.get("login")
            or "Пользователь"
        )
    return (
        session.get("full_name")
        or session.get("username")
        or session.get("login")
        or "Пользователь"
    )


def current_role():
    user = current_user()
    if not user:
        return ""
    return str(user.get("role") or "").strip()


def is_admin():
    role = (current_role() or "").strip().lower()
    return role in ["администратор", "admin"]


def is_request_initiator():
    role = (current_role() or "").strip().lower()
    return role in [
        "инициатор заявки",
        "initiator",
        "request_initiator",
        "dispatcher",
        "requester",
    ]


def is_internal_approver():
    role = (current_role() or "").strip().lower()
    return role in [
        "согласующий по внутреннему транспорту",
        "internal_approver",
    ]


def is_external_approver():
    role = (current_role() or "").strip().lower()
    return role in [
        "согласующий по стороннему транспорту",
        "external_approver",
    ]


def is_fuel_operator():
    role = (current_role() or "").strip().lower()
    return role in [
        "оператор заправки",
        "fuel_operator",
        "operator",
        "fueler",
    ]


def is_controller():
    role = (current_role() or "").strip().lower()
    return role in [
        "контролёр",
        "контролер",
        "controller",
    ]


def can_create_request():
    return is_request_initiator()


def normalize_approval_type(value):
    v = (value or "").strip().lower()
    if v == "external":
        return "external"
    return "internal"


def can_check_request(row):
    if not is_controller():
        return False
    return (row.get("status") or "") in ["fueled", "driver_confirmed"]

def can_see_request_row(row):
    status = (row.get("status") or "").strip()
    approval_type = normalize_approval_type(row.get("approval_type"))

    if status == "checked":
        return False

    if is_admin():
        return True

    if is_request_initiator():
        return status in ["new", "approved", "fueled", "driver_confirmed", "rejected"]

    if is_internal_approver():
        return status in ["new", "approved"] and approval_type == "internal"

    if is_external_approver():
        return status in ["new", "approved"] and approval_type == "external"

    if is_fuel_operator():
        return status in ["approved", "fueled"]

    if is_controller():
        return status in ["fueled", "driver_confirmed"]

    return False


def can_approve_request(row):
    if (row.get("status") or "") != "new":
        return False

    approval_type = normalize_approval_type(row.get("approval_type"))

    if is_internal_approver():
        return approval_type == "internal"

    if is_external_approver():
        return approval_type == "external"

    return False


def can_fuel_request(row):
    if not is_fuel_operator():
        return False
    return (row.get("status") or "") == "approved"


def status_label(status):
    if status == "new":
        return "Новая"
    if status == "approved":
        return "Согласована"
    if status == "fueled":
        return "Заправлена"
    if status == "driver_confirmed":
        return "Подтверждена водителем"
    if status == "checked":
        return "Закрыта"
    if status == "rejected":
        return "Отклонена"
    return status or "—"


def status_stage_label(status):
    if status == "new":
        return "Ожидает согласования"
    if status == "approved":
        return "Ожидает заправки"
    if status == "fueled":
        return "Ожидает контроля"
    if status == "driver_confirmed":
        return "Ожидает контроля"
    if status == "checked":
        return "Заявка закрыта"
    if status == "rejected":
        return "Отклонена"
    return "—"


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
            r.approved_liters,
            r.actual_liters,
            r.requested_by,
            r.approved_by,
            r.fueler_name,
            r.controller_name,
            r.status,
            r.created_at,
            r.project_name,
            r.fuel_supplier,
            COALESCE(r.approval_type, 'internal') AS approval_type
        FROM fuel_requests r
        LEFT JOIN objects o ON o.id = r.object_id
        LEFT JOIN vehicles v ON v.id = r.vehicle_id
        WHERE COALESCE(r.status, 'new') <> 'checked'
        ORDER BY r.id DESC
    """)

    visible_rows = [r for r in rows if can_see_request_row(r)]

    content = """
    <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; gap:10px;'>
        <h2 style='margin:0;'>Заявки</h2>
    """

    if can_create_request():
        content += """
        <a href='/requests/new' style='text-decoration:none; padding:8px 12px; border:1px solid #ccc; border-radius:8px;'>
            ➕ Новая заявка
        </a>
        """

    content += "</div>"

    if visible_rows:
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
                <th>Тип</th>
                <th>Подал</th>
                <th>Действия</th>
            </tr>
        """

        for r in visible_rows:
            transport = f"{r['plate_number'] or ''} {r['vehicle_name'] or ''}".strip()
            fact_text = f" / факт {r['actual_liters']} л" if r["actual_liters"] else ""
            norm_text = ""
            if r["base_consumption"]:
                norm_text = f"{r['base_consumption']} {meter_unit(r['meter_type'])}"

            approval_type_label = (
                "Сторонний транспорт"
                if normalize_approval_type(r["approval_type"]) == "external"
                else "Внутренний транспорт"
            )

            action_btn = ""
            if can_approve_request(r):
                action_btn = f"<a href='/requests/{r['id']}' style='margin-left:8px;'>Согласовать</a>"
            elif can_fuel_request(r):
                action_btn = f"<a href='/requests/{r['id']}' style='margin-left:8px;'>Заправить</a>"

            content += f"""
            <tr>
                <td>{r['id']}</td>
                <td>
                    <div style='display:flex; flex-direction:column; gap:4px;'>
                        <span style='display:inline-block; padding:3px 8px; border-radius:999px; color:#fff; background:{status_color(r["status"])}; width:fit-content;'>
                            {status_label(r['status'])}
                        </span>
                        <span style='font-size:12px; color:#666;'>
                            {status_stage_label(r['status'])}
                        </span>
                    </div>
                </td>
                <td>{r['object_name'] or '—'}</td>
                <td>{transport or '—'}</td>
                <td>{norm_text or '—'}</td>
                <td>{r['requested_liters'] or '—'} л{fact_text}</td>
                <td>{r['fuel_supplier'] or '—'}</td>
                <td>{approval_type_label}</td>
                <td>{r['requested_by'] or '—'}</td>
                <td style='white-space:nowrap;'>
                    <a href='/requests/{r["id"]}'>Подробнее</a>
                    {action_btn}
                </td>
            </tr>
            """

        content += "</table></div>"
    else:
        content += "<p>Активных заявок нет.</p>"

    return render_page("Заявки", content)


@requests_bp.route("/requests/new", methods=["GET", "POST"])
@login_required
def new_request():
    if not can_create_request():
        return render_page("Доступ запрещен", "<p>У вас нет прав на создание заявки.</p>")

    if request.method == "POST":
        object_name = (request.form.get("object_name") or "").strip()
        vehicle_label = (request.form.get("vehicle_label") or "").strip()

        requested_liters = request.form.get("requested_liters") or 0
        requested_by = request.form.get("requested_by") or ""
        project_name = request.form.get("project_name") or ""
        fuel_supplier = request.form.get("fuel_supplier") or ""
        tank_balance = request.form.get("tank_balance") or ""
        route_work = request.form.get("route_work") or ""
        comment = request.form.get("comment") or ""
        approval_type = normalize_approval_type(request.form.get("approval_type"))

        obj = fetch_one("""
            SELECT id, name
            FROM objects
            WHERE name = %s
            LIMIT 1
        """, (object_name,))

        veh = fetch_one("""
            SELECT
                id,
                vehicle_name,
                vehicle_type,
                plate_number
            FROM vehicles
            WHERE CONCAT(
                COALESCE(plate_number, ''),
                ' | ',
                COALESCE(vehicle_name, ''),
                ' | ',
                COALESCE(vehicle_type, '')
            ) = %s
            LIMIT 1
        """, (vehicle_label,))

        if not obj:
            return render_page(
                "Ошибка",
                "<p>Объект не выбран из списка. Вернитесь назад и выберите объект из поиска.</p>"
            )

        if not veh:
            return render_page(
                "Ошибка",
                "<p>Транспорт не выбран из списка. Вернитесь назад и выберите транспорт из поиска.</p>"
            )

        if not fuel_supplier:
            return render_page(
                "Ошибка",
                "<p>Выберите компанию, за чей счет выдается топливо.</p>"
            )

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
                approval_type,
                status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'new')
        """, (
            obj["id"],
            veh["id"],
            requested_liters,
            requested_by,
            project_name,
            fuel_supplier,
            full_comment,
            approval_type
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
            plate_number
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

    content = """
    <div style='max-width:760px; margin:0 auto;'>
        <h2 style='margin-bottom:16px;'>Новая заявка</h2>

        <form method='post' style='display:flex; flex-direction:column; gap:12px;'>

            <div>
                <label><b>1. Объект заправки:</b></label><br>
                <input
                    type='text'
                    name='object_name'
                    list='objects_list'
                    placeholder='Начните вводить название объекта'
                    autocomplete='off'
                    style='width:100%; padding:8px;'
                    required
                >
                <datalist id='objects_list'>
    """

    for o in objects:
        content += f"<option value='{o['name']}'></option>"

    content += """
                </datalist>
            </div>

            <div>
                <label><b>2. Транспорт:</b></label><br>
                <input
                    type='text'
                    name='vehicle_label'
                    list='vehicles_list'
                    placeholder='Начните вводить гос.номер, транспорт или тип'
                    autocomplete='off'
                    style='width:100%; padding:8px;'
                    required
                >
                <datalist id='vehicles_list'>
    """

    for v in vehicles:
        label = f"{v['plate_number'] or ''} | {v['vehicle_name'] or ''} | {v['vehicle_type'] or ''}"
        content += f"<option value='{label}'></option>"

    content += """
                </datalist>
            </div>

            <div>
                <label><b>3. Тип согласования:</b></label><br>
                <select name='approval_type' style='width:100%; padding:8px;' required>
                    <option value='internal'>Внутренний транспорт</option>
                    <option value='external'>Сторонний транспорт</option>
                </select>
            </div>

            <div>
                <label><b>4. Остаток в баке (л):</b></label><br>
                <input type='number' step='0.01' name='tank_balance' style='width:100%; padding:8px;'>
            </div>

            <div>
                <label><b>5. Запрашиваемое количество топлива (л):</b></label><br>
                <input type='number' step='0.01' name='requested_liters' required style='width:100%; padding:8px;'>
            </div>

            <div>
                <label><b>6. Маршрут / объем работ:</b></label><br>
                <input type='text' name='route_work' style='width:100%; padding:8px;'>
            </div>

            <div>
                <label><b>7. Кто подает заявку:</b></label><br>
                <select name='requested_by' required style='width:100%; padding:8px;'>
                    <option value=''>-- Выберите --</option>
    """

    for u in users:
        content += f"<option value='{u['full_name']}'>{u['full_name']}</option>"

    content += """
                </select>
            </div>

            <div>
                <label><b>8. Проект:</b></label><br>
                <input type='text' name='project_name' style='width:100%; padding:8px;'>
            </div>

            <div>
                <label><b>9. За чей счет выдается топливо:</b></label><br>
                <select name='fuel_supplier' style='width:100%; padding:8px;' required>
                    <option value=''>-- Выберите компанию --</option>
    """

    for c in companies:
        content += f"<option value='{c['name']}'>{c['name']}</option>"

    content += """
                </select>
            </div>

            <div>
                <label><b>10. Комментарий:</b></label><br>
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
            v.load_coeff_heavy,
            COALESCE(r.approval_type, 'internal') AS approval_type
        FROM fuel_requests r
        LEFT JOIN objects o ON o.id = r.object_id
        LEFT JOIN vehicles v ON v.id = r.vehicle_id
        WHERE r.id = %s
    """, (request_id,))

    if not r:
        return render_page("Ошибка", "<p>Заявка не найдена.</p>")

    if not can_see_request_row(r):
        return render_page("Доступ запрещен", "<p>У вас нет прав на просмотр этой заявки.</p>")

    companies = fetch_all("""
        SELECT id, name
        FROM companies
        ORDER BY name
    """)

    transport = f"{r['plate_number'] or ''} {r['vehicle_name'] or ''}".strip()
    base_norm = "—"
    if r["base_consumption"]:
        base_norm = f"{r['base_consumption']} {meter_unit(r['meter_type'])}"

    approval_type_label = (
        "Сторонний транспорт"
        if normalize_approval_type(r["approval_type"]) == "external"
        else "Внутренний транспорт"
    )

    content = f"""
    <div style='max-width:820px; margin:0 auto;'>
        <div style='display:flex; justify-content:space-between; align-items:center; gap:10px; margin-bottom:14px;'>
            <h2 style='margin:0;'>Заявка №{r['id']}</h2>
            <a href='/requests'>← Назад к списку</a>
        </div>

        <div style='border:1px solid #ddd; border-radius:10px; padding:14px; background:#fff;'>
            <div style='margin-bottom:10px; display:flex; flex-direction:column; gap:6px;'>
                <span style='display:inline-block; padding:5px 10px; border-radius:999px; color:#fff; background:{status_color(r["status"])}; width:fit-content;'>
                    {status_label(r['status'])}
                </span>
                <span style='font-size:13px; color:#666;'>
                    {status_stage_label(r['status'])}
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
                <tr><td style='padding:6px;'><b>За чей счет выдается топливо</b></td><td style='padding:6px;'>{r['fuel_supplier'] or '—'}</td></tr>
                <tr><td style='padding:6px;'><b>Тип согласования</b></td><td style='padding:6px;'>{approval_type_label}</td></tr>
                <tr><td style='padding:6px;'><b>Проект</b></td><td style='padding:6px;'>{r['project_name'] or '—'}</td></tr>
                <tr><td style='padding:6px;'><b>Комментарий</b></td><td style='padding:6px;'>{r['request_comment'] or '—'}</td></tr>
            </table>
        </div>

        <div style='border:1px solid #ddd; border-radius:10px; padding:14px; background:#fff; margin-top:14px;'>
            <h3 style='margin-top:0;'>Ход согласования</h3>
            <table style='width:100%; border-collapse:collapse; font-size:14px;'>
                <tr><td style='padding:6px; width:260px;'><b>Заявку подал</b></td><td style='padding:6px;'>{r['requested_by'] or '—'}</td></tr>
                <tr><td style='padding:6px;'><b>Согласовал</b></td><td style='padding:6px;'>{r['approved_by'] or '—'}</td></tr>
                <tr><td style='padding:6px;'><b>Заправил</b></td><td style='padding:6px;'>{r['fueler_name'] or '—'}</td></tr>
                <tr><td style='padding:6px;'><b>Подтверждение водителя</b></td><td style='padding:6px;'>{"—" if "driver_name" not in r.keys() else (r["driver_name"] or "—")}</td></tr>
                <tr><td style='padding:6px;'><b>Проверил</b></td><td style='padding:6px;'>{r['controller_name'] or '—'}</td></tr>
            </table>
        </div>

        <div style='border:1px solid #ddd; border-radius:10px; padding:14px; background:#fff; margin-top:14px;'>
            <h3 style='margin-top:0;'>Даты</h3>
            <table style='width:100%; border-collapse:collapse; font-size:14px;'>
                <tr><td style='padding:6px; width:260px;'><b>Создана</b></td><td style='padding:6px;'>{r['created_at'] or '—'}</td></tr>
                <tr><td style='padding:6px;'><b>Согласована</b></td><td style='padding:6px;'>{r['approved_at'] or '—'}</td></tr>
                <tr><td style='padding:6px;'><b>Заправлена</b></td><td style='padding:6px;'>{r['fueled_at'] or '—'}</td></tr>
                <tr><td style='padding:6px;'><b>Проверена</b></td><td style='padding:6px;'>{r['checked_at'] or '—'}</td></tr>
            </table>
        </div>
    """

    if can_approve_request(r):
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
                    <label><b>За чей счет выдается топливо:</b></label><br>
                    <select name='fuel_supplier' style='width:100%; padding:8px;' required>
                        <option value=''>-- Выберите компанию --</option>
        """

        for c in companies:
            selected = "selected" if (r["fuel_supplier"] or "") == c["name"] else ""
            content += f"<option value='{c['name']}' {selected}>{c['name']}</option>"

        content += f"""
                    </select>
                </div>

                <div style='margin-bottom:10px;'>
                    <label><b>Тип согласования:</b></label><br>
                    <select name='approval_type' style='width:100%; padding:8px;'>
                        <option value='internal' {"selected" if normalize_approval_type(r["approval_type"]) == "internal" else ""}>Внутренний транспорт</option>
                        <option value='external' {"selected" if normalize_approval_type(r["approval_type"]) == "external" else ""}>Сторонний транспорт</option>
                    </select>
                </div>

                <div style='margin-bottom:10px;'>
                    <label><b>Комментарий согласующего:</b></label><br>
                    <textarea name='approval_comment' rows='4'
                              style='width:100%; padding:8px;'></textarea>
                </div>

                <div style='display:flex; gap:8px; flex-wrap:wrap;'>
                    <button type='submit' name='decision' value='approve'
                            style='padding:10px 14px; border:none; border-radius:8px; background:#1565c0; color:white;'>
                        Согласовать
                    </button>

                    <button type='submit' name='decision' value='approve_adjusted'
                            style='padding:10px 14px; border:none; border-radius:8px; background:#ef6c00; color:white;'>
                        Согласовать с корректировкой
                    </button>

                    <button type='submit' name='decision' value='reject'
                            style='padding:10px 14px; border:none; border-radius:8px; background:#c62828; color:white;'>
                        Отклонить
                    </button>
                </div>
            </form>
        </div>
        """

    if can_fuel_request(r):
        content += f"""
        <div style='border:1px solid #ddd; border-radius:10px; padding:14px; background:#fff; margin-top:14px;'>
            <h3 style='margin-top:0;'>Заправка</h3>

            <form method='post' action='/requests/{r["id"]}/fuel'>
                <div style='margin-bottom:10px;'>
                    <label><b>Согласовано литров:</b></label><br>
                    <input type='text' value='{r["approved_liters"] or r["requested_liters"] or ""}' disabled
                           style='width:100%; padding:8px; background:#f5f5f5;'>
                </div>

                <div style='margin-bottom:10px;'>
                    <label><b>Фактически отпущено литров:</b></label><br>
                    <input type='number' step='0.01' name='actual_liters'
                           value='{r["approved_liters"] or r["requested_liters"] or ""}'
                           style='width:100%; padding:8px;' required>
                </div>

                <div style='margin-bottom:10px;'>
                    <label><b>Комментарий оператора:</b></label><br>
                    <textarea name='fuel_comment' rows='4'
                              style='width:100%; padding:8px;'></textarea>
                </div>

                <div>
                    <button type='submit'
                            style='padding:10px 14px; border:none; border-radius:8px; background:#ef6c00; color:white;'>
                        Заправлено
                    </button>
                </div>
            </form>
        </div>
        """

    if can_check_request(r):
        content += f"""
        <div style='border:1px solid #ddd; border-radius:10px; padding:14px; background:#fff; margin-top:14px;'>
            <h3 style='margin-top:0;'>Контроль</h3>

            <form method='post' action='/requests/{r["id"]}/check'>
                <div style='margin-bottom:10px;'>
                    <label><b>Фактически отпущено:</b></label><br>
                    <input type='text' value='{r["actual_liters"] or ""} л' disabled
                           style='width:100%; padding:8px; background:#f5f5f5;'>
                </div>

                <div style='margin-bottom:10px;'>
                    <label><b>Комментарий контролёра:</b></label><br>
                    <textarea name='check_comment' rows='4'
                              style='width:100%; padding:8px;'></textarea>
                </div>

                <div>
                    <button type='submit'
                            style='padding:10px 14px; border:none; border-radius:8px; background:#2e7d32; color:white;'>
                        Проверено / Закрыть
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
        SELECT
            id,
            status,
            requested_liters,
            COALESCE(approval_type, 'internal') AS approval_type
        FROM fuel_requests
        WHERE id = %s
    """, (request_id,))

    if not req:
        return render_page("Ошибка", "<p>Заявка не найдена.</p>")

    if not can_approve_request(req):
        return render_page("Доступ запрещен", "<p>У вас нет прав на согласование этой заявки.</p>")

    decision = request.form.get("decision")
    approved_liters = request.form.get("approved_liters") or req["requested_liters"]
    fuel_supplier = request.form.get("fuel_supplier") or ""
    approval_type = normalize_approval_type(request.form.get("approval_type") or req["approval_type"])
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


@requests_bp.route("/requests/<int:request_id>/fuel", methods=["POST"])
@login_required
def request_fuel(request_id):
    req = fetch_one("""
        SELECT
            id,
            status,
            requested_liters,
            approved_liters,
            COALESCE(approval_type, 'internal') AS approval_type
        FROM fuel_requests
        WHERE id = %s
    """, (request_id,))

    if not req:
        return render_page("Ошибка", "<p>Заявка не найдена.</p>")

    if not can_fuel_request(req):
        return render_page("Доступ запрещен", "<p>У вас нет прав на выполнение заправки по этой заявке.</p>")

    actual_liters = request.form.get("actual_liters") or 0
    operator_name = current_user_name()

    execute_query("""
        UPDATE fuel_requests
        SET
            status = 'fueled',
            actual_liters = %s,
            fueler_name = %s,
            fueled_at = CURRENT_TIMESTAMP
        WHERE id = %s
    """, (
        actual_liters,
        operator_name,
        request_id
    ))

    return redirect(f"/requests/{request_id}")


@requests_bp.route("/requests/<int:request_id>/check", methods=["POST"])
@login_required
def request_check(request_id):
    req = fetch_one("""
        SELECT
            r.id,
            r.status,
            r.actual_liters,
            r.vehicle_id,
            r.object_id,
            o.name AS object_name,
            v.plate_number,
            v.vehicle_name
        FROM fuel_requests r
        LEFT JOIN objects o ON o.id = r.object_id
        LEFT JOIN vehicles v ON v.id = r.vehicle_id
        WHERE r.id = %s
    """, (request_id,))

    if not req:
        return render_page("Ошибка", "<p>Заявка не найдена.</p>")

    if not can_check_request(req):
        return render_page("Доступ запрещен", "<p>У вас нет прав на проверку этой заявки.</p>")

    controller_name = current_user_name()
    check_comment = request.form.get("check_comment") or ""

    vehicle_text = f"{req['plate_number'] or ''} {req['vehicle_name'] or ''}".strip()
    object_name = (req["object_name"] or "").strip()

    if not vehicle_text:
        return render_page("Ошибка", "<p>Не найден транспорт для записи в журнал.</p>")

    if not object_name:
        return render_page("Ошибка", "<p>Не найден объект для записи в журнал.</p>")

    execute_query("""
        UPDATE fuel_requests
        SET
            status = 'checked',
            controller_name = %s,
            checked_at = CURRENT_TIMESTAMP,
            check_comment = %s
        WHERE id = %s
    """, (
        controller_name,
        check_comment,
        request_id
    ))

    execute_query("""
        INSERT INTO fuel_transactions (
            vehicle,
            object_name,
            liters,
            speedometer,
            entered_by,
            dispatcher_status,
            comment,
            created_at,
            entry_type
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), %s)
    """, (
        vehicle_text,
        object_name,
        req["actual_liters"] or 0,
        None,
        controller_name,
        "approved",
        check_comment,
        "chiqim"
    ))

    return redirect("/requests")
