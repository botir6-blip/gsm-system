from flask import Blueprint, request, redirect, url_for, flash, session
from db import fetch_all, fetch_one, execute_query
from auth import login_required, role_required
from layout import render_page

requests_bp = Blueprint("requests_bp", __name__)


def get_current_user():
    return fetch_one("""
        SELECT id, full_name, role, company_id
        FROM users
        WHERE id = %s
    """, (session["user_id"],))


def get_company_stations(company_id):
    return fetch_all("""
        SELECT fs.id, fs.name, fs.company_id, fs.operator_user_id,
               u.full_name AS operator_name
        FROM fuel_stations fs
        LEFT JOIN users u ON u.id = fs.operator_user_id
        WHERE fs.company_id = %s
          AND fs.is_active = TRUE
        ORDER BY fs.name
    """, (company_id,))


@requests_bp.route("/requests")
@login_required
def requests_list():
    user = get_current_user()
    role = user["role"]
    company_id = user["company_id"]
    user_id = user["id"]

    base_sql = """
        SELECT
            fr.*,
            ru.full_name AS requester_name,
            au.full_name AS approver_name,
            fu.full_name AS fueler_name,
            du.full_name AS driver_confirmer_name,
            cu.name AS requester_company_name,
            fp.name AS fuel_provider_company_name,
            fs.name AS fuel_station_name,
            fs.company_id AS station_company_id
        FROM fuel_requests fr
        LEFT JOIN users ru ON ru.id = fr.requester_user_id
        LEFT JOIN users au ON au.id = fr.approved_by_user_id
        LEFT JOIN users fu ON fu.id = fr.fueled_by_user_id
        LEFT JOIN users du ON du.id = fr.driver_confirmed_by_user_id
        LEFT JOIN companies cu ON cu.id = fr.requester_company_id
        LEFT JOIN companies fp ON fp.id = fr.fuel_provider_company_id
        LEFT JOIN fuel_stations fs ON fs.id = fr.fuel_station_id
    """

    if role in ["admin"]:
        rows = fetch_all(base_sql + " ORDER BY fr.created_at DESC")
    elif role in ["manager", "director", "deputy"]:
        # Руководитель видит заявки только своей компании
        rows = fetch_all(base_sql + """
            WHERE fr.requester_company_id = %s
               OR fr.fuel_provider_company_id = %s
            ORDER BY fr.created_at DESC
        """, (company_id, company_id))
    elif role in ["operator", "fuel_operator", "zapravka_operator"]:
        # Оператор видит только:
        # 1) одобренные заявки
        # 2) направленные на закрепленную за ним АЗС
        # 3) АЗС должна принадлежать его компании
        rows = fetch_all(base_sql + """
            WHERE fr.status IN ('approved', 'fueling')
              AND fs.operator_user_id = %s
              AND fs.company_id = %s
            ORDER BY fr.created_at DESC
        """, (user_id, company_id))
    elif role in ["dispatcher", "ats_dispatcher"]:
        rows = fetch_all(base_sql + """
            WHERE fr.status IN ('fueled', 'driver_confirmed')
              AND (
                    fr.requester_company_id = %s
                    OR fr.fuel_provider_company_id = %s
                  )
            ORDER BY fr.created_at DESC
        """, (company_id, company_id))
    else:
        # Обычный сотрудник / ответственный — только свои заявки
        rows = fetch_all(base_sql + """
            WHERE fr.requester_user_id = %s
            ORDER BY fr.created_at DESC
        """, (user_id,))

    html = """
    <h2>Заявки</h2>
    <div class="table-responsive">
    <table class="table table-bordered table-sm">
        <thead>
            <tr>
                <th>ID</th>
                <th>Дата</th>
                <th>Заявитель</th>
                <th>Компания</th>
                <th>Запрошено</th>
                <th>Одобрено</th>
                <th>Заправлено</th>
                <th>Поставщик топлива</th>
                <th>АЗС</th>
                <th>Статус</th>
                <th>Действие</th>
            </tr>
        </thead>
        <tbody>
    """

    stations = []
    if role in ["manager", "director", "deputy"]:
        stations = get_company_stations(company_id)

    for r in rows:
        actions = ""

        if role in ["manager", "director", "deputy"] and r["status"] == "new":
            options = '<option value="">Выберите АЗС</option>'
            for s in stations:
                options += f'<option value="{s["id"]}">{s["name"]}</option>'

            actions += f"""
            <form method="post" action="/requests/{r['id']}/approve" style="display:flex; gap:6px; flex-wrap:wrap;">
                <input type="number" step="0.01" min="0" name="approved_liters"
                       value="{r['requested_liters'] or ''}" placeholder="Литры" required>
                <select name="fuel_station_id" required>
                    {options}
                </select>
                <button type="submit" class="btn btn-success btn-sm">Одобрить</button>
            </form>
            """

        if role in ["operator", "fuel_operator", "zapravka_operator"] and r["status"] == "approved":
            actions += f"""
            <form method="post" action="/requests/{r['id']}/fuel" style="display:flex; gap:6px; flex-wrap:wrap;">
                <input type="number" step="0.01" min="0" name="fueled_liters"
                       value="{r['approved_liters'] or ''}" placeholder="Заправлено (литры)" required>
                <button type="submit" class="btn btn-primary btn-sm">Заправить</button>
            </form>
            """

        if role in ["dispatcher", "ats_dispatcher"] and r["status"] == "driver_confirmed":
            actions += f"""
            <form method="post" action="/requests/{r['id']}/dispatcher-check">
                <button type="submit" class="btn btn-dark btn-sm">Проверено</button>
            </form>
            """

        html += f"""
            <tr>
                <td>{r['id']}</td>
                <td>{r['created_at'].strftime('%Y-%m-%d %H:%M') if r['created_at'] else ''}</td>
                <td>{r.get('requester_name') or ''}</td>
                <td>{r.get('requester_company_name') or ''}</td>
                <td>{r.get('requested_liters') or ''}</td>
                <td>{r.get('approved_liters') or ''}</td>
                <td>{r.get('fueled_liters') or ''}</td>
                <td>{r.get('fuel_provider_company_name') or ''}</td>
                <td>{r.get('fuel_station_name') or ''}</td>
                <td>{r.get('status') or ''}</td>
                <td>{actions}</td>
            </tr>
        """

    html += """
        </tbody>
    </table>
    </div>
    """

    return render_page("Заявки", html)


@requests_bp.route("/requests/<int:request_id>/approve", methods=["POST"])
@login_required
@role_required("manager", "director", "deputy", "admin")
def approve_request(request_id):
    user = get_current_user()

    fuel_station_id = request.form.get("fuel_station_id")
    approved_liters = request.form.get("approved_liters")

    if not fuel_station_id:
        flash("АЗС не выбрана", "danger")
        return redirect(url_for("requests_bp.requests_list"))

    station = fetch_one("""
        SELECT id, name, company_id, operator_user_id
        FROM fuel_stations
        WHERE id = %s AND is_active = TRUE
    """, (fuel_station_id,))

    if not station:
        flash("АЗС не найдена", "danger")
        return redirect(url_for("requests_bp.requests_list"))

    # Самое важное:
    # руководитель может выбрать только АЗС своей компании
    if user["role"] != "admin" and station["company_id"] != user["company_id"]:
        flash("Вы можете выбрать только АЗС своей компании", "danger")
        return redirect(url_for("requests_bp.requests_list"))

    execute_query("""
        UPDATE fuel_requests
        SET status = 'approved',
            fuel_station_id = %s,
            approved_liters = %s,
            approved_by_user_id = %s,
            approved_at = CURRENT_TIMESTAMP
        WHERE id = %s
    """, (fuel_station_id, approved_liters, user["id"], request_id))

    flash("Заявка одобрена и отправлена на выбранную АЗС", "success")
    return redirect(url_for("requests_bp.requests_list"))


@requests_bp.route("/requests/<int:request_id>/fuel", methods=["POST"])
@login_required
@role_required("operator", "fuel_operator", "zapravka_operator", "admin")
def fuel_request(request_id):
    user = get_current_user()
    fueled_liters = request.form.get("fueled_liters")

    # Оператор может обрабатывать только свои заявки своей компании
    req = fetch_one("""
        SELECT fr.id, fr.status, fr.fuel_station_id, fs.operator_user_id, fs.company_id
        FROM fuel_requests fr
        JOIN fuel_stations fs ON fs.id = fr.fuel_station_id
        WHERE fr.id = %s
    """, (request_id,))

    if not req:
        flash("Заявка не найдена", "danger")
        return redirect(url_for("requests_bp.requests_list"))

    if user["role"] != "admin":
        if req["operator_user_id"] != user["id"] or req["company_id"] != user["company_id"]:
            flash("Эта заявка вам не принадлежит", "danger")
            return redirect(url_for("requests_bp.requests_list"))

    execute_query("""
        UPDATE fuel_requests
        SET status = 'fueled',
            fueled_liters = %s,
            fueled_by_user_id = %s,
            fueled_at = CURRENT_TIMESTAMP
        WHERE id = %s
    """, (fueled_liters, user["id"], request_id))

    flash("Данные о заправке сохранены", "success")
    return redirect(url_for("requests_bp.requests_list"))


@requests_bp.route("/requests/<int:request_id>/driver-confirm", methods=["POST"])
@login_required
def driver_confirm_request(request_id):
    user = get_current_user()

    # Здесь потом можно жестче связать с transport/driver
    req = fetch_one("""
        SELECT id, status
        FROM fuel_requests
        WHERE id = %s
    """, (request_id,))

    if not req:
        flash("Заявка не найдена", "danger")
        return redirect(url_for("requests_bp.requests_list"))

    if req["status"] != "fueled":
        flash("Заправка еще не выполнена", "warning")
        return redirect(url_for("requests_bp.requests_list"))

    execute_query("""
        UPDATE fuel_requests
        SET status = 'driver_confirmed',
            driver_confirmed_by_user_id = %s,
            driver_confirmed_at = CURRENT_TIMESTAMP
        WHERE id = %s
    """, (user["id"], request_id))

    flash("Получение подтверждено", "success")
    return redirect(url_for("requests_bp.requests_list"))


@requests_bp.route("/requests/<int:request_id>/dispatcher-check", methods=["POST"])
@login_required
@role_required("dispatcher", "ats_dispatcher", "admin")
def dispatcher_check_request(request_id):
    user = get_current_user()

    req = fetch_one("""
        SELECT id, requester_company_id, fuel_provider_company_id, status
        FROM fuel_requests
        WHERE id = %s
    """, (request_id,))

    if not req:
        flash("Заявка не найдена", "danger")
        return redirect(url_for("requests_bp.requests_list"))

    if user["role"] != "admin":
        if user["company_id"] not in [req["requester_company_id"], req["fuel_provider_company_id"]]:
            flash("Вы не можете проверять чужую заявку", "danger")
            return redirect(url_for("requests_bp.requests_list"))

    execute_query("""
        UPDATE fuel_requests
        SET status = 'closed',
            dispatcher_checked_by_user_id = %s,
            dispatcher_checked_at = CURRENT_TIMESTAMP
        WHERE id = %s
    """, (user["id"], request_id))

    flash("Заявка завершена", "success")
    return redirect(url_for("requests_bp.requests_list"))

@requests_bp.route("/requests/new", methods=["GET", "POST"])
@login_required
def new_request():
    user = get_current_user()

    if request.method == "POST":
        object_name = (request.form.get("object_name") or "").strip()
        vehicle_label = (request.form.get("vehicle_label") or "").strip()

        requested_liters = request.form.get("requested_liters") or 0
        requested_by = (request.form.get("requested_by") or "").strip()
        project_name = (request.form.get("project_name") or "").strip()
        fuel_provider_company_id = request.form.get("fuel_provider_company_id") or None
        tank_balance = (request.form.get("tank_balance") or "").strip()
        route_work = (request.form.get("route_work") or "").strip()
        comment = (request.form.get("comment") or "").strip()
        approval_type = (request.form.get("approval_type") or "internal").strip()

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
                plate_number
            FROM vehicles
            WHERE plate_number = %s
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

        if not fuel_provider_company_id:
            return render_page(
                "Ошибка",
                "<p>Выберите компанию, за чей счет выдается топливо.</p>"
            )

        full_comment = f"""Подал: {requested_by or (user.get('full_name') or '')}
Тип заявки: {"Сторонний транспорт" if approval_type == "external" else "Внутренний транспорт"}
Остаток в баке: {tank_balance}
Маршрут / объем работ: {route_work}
Комментарий: {comment}"""

        execute_query("""
            INSERT INTO fuel_requests (
                requester_user_id,
                requester_company_id,
                object_id,
                vehicle_id,
                project_name,
                requested_liters,
                fuel_provider_company_id,
                comment,
                status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'new')
        """, (
            user["id"],
            user["company_id"],
            obj["id"],
            veh["id"],
            project_name,
            requested_liters,
            fuel_provider_company_id,
            full_comment
        ))

        flash("Заявка создана", "success")
        return redirect("/requests")

    objects = fetch_all("""
        SELECT id, name
        FROM objects
        WHERE is_active = TRUE
        ORDER BY name
    """)

    vehicles = fetch_all("""
        SELECT
            id,
            vehicle_name,
            plate_number,
            fuel_norm
        FROM vehicles
        WHERE is_active = TRUE
        ORDER BY plate_number
    """)

    companies = fetch_all("""
        SELECT id, name
        FROM companies
        WHERE is_active = TRUE
        ORDER BY name
    """)

    current_user_name = user.get("full_name") or ""

    content = f"""
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
        plate = v.get('plate_number') or ''
        name = v.get('vehicle_name') or ''
        norm = v.get('fuel_norm') or ''

        if plate:
            content += f"<option value='{plate}'>{plate} | {name} | норма: {norm}</option>"

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
    """

    content += f"""
            <div>
                <label><b>4. Кто подает заявку:</b></label><br>
                <input
                    type='text'
                    name='requested_by'
                    value='{current_user_name}'
                    placeholder='ФИО'
                    style='width:100%; padding:8px;'
                >
            </div>
    """

    content += """
            <div>
                <label><b>5. Проект:</b></label><br>
                <input
                    type='text'
                    name='project_name'
                    placeholder='Название проекта'
                    style='width:100%; padding:8px;'
                >
            </div>

            <div>
                <label><b>6. Количество литров:</b></label><br>
                <input
                    type='number'
                    step='0.01'
                    min='0'
                    name='requested_liters'
                    style='width:100%; padding:8px;'
                    required
                >
            </div>

            <div>
                <label><b>7. За чей счет выдается топливо:</b></label><br>
                <select name='fuel_provider_company_id' style='width:100%; padding:8px;' required>
                    <option value=''>Выберите компанию</option>
    """

    for c in companies:
        content += f"<option value='{c['id']}'>{c['name']}</option>"

    content += """
                </select>
            </div>

            <div>
                <label><b>8. Остаток в баке:</b></label><br>
                <input
                    type='text'
                    name='tank_balance'
                    placeholder='Например: 40 л'
                    style='width:100%; padding:8px;'
                >
            </div>

            <div>
                <label><b>9. Маршрут / объем работ:</b></label><br>
                <textarea
                    name='route_work'
                    rows='3'
                    placeholder='Укажите маршрут или объем работ'
                    style='width:100%; padding:8px;'
                ></textarea>
            </div>

            <div>
                <label><b>10. Комментарий:</b></label><br>
                <textarea
                    name='comment'
                    rows='4'
                    placeholder='Дополнительная информация'
                    style='width:100%; padding:8px;'
                ></textarea>
            </div>

            <div style='display:flex; gap:10px; flex-wrap:wrap; margin-top:8px;'>
                <button type='submit' class='btn btn-success'>Отправить заявку</button>
                <a href='/requests' class='btn btn-secondary'>Назад</a>
            </div>

        </form>
    </div>
    """

    return render_page("Новая заявка", content)
