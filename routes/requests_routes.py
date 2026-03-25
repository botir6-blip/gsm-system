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

@requests_bp.route("/requests/new")
@login_required
def new_request_redirect():
    return redirect("/requests")
