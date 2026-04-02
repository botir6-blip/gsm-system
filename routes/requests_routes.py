from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, request, redirect, url_for, flash

from auth import login_required, get_current_user, get_scope_ids
from db import (
    DEFAULT_DENSITY,
    execute_query,
    execute_query_returning,
    fetch_all,
    fetch_one,
)
from layout import render_page

requests_bp = Blueprint("requests_bp", __name__)

REQUEST_TYPE_LABELS = {
    "external_vehicle_from_our_point": "Транспорт внешней компании с нашего пункта",
    "our_vehicle_from_external_point": "Наш транспорт с внешнего пункта",
}

REQUEST_STATUS_LABELS = {
    "draft": "Черновик",
    "pending_approval": "Ожидает согласования",
    "approved": "Согласовано",
    "rejected": "Отклонено",
    "fueling_done": "Заправка выполнена",
    "checked": "Проверено",
    "cancelled": "Отменено",
}


def _parse_page():
    try:
        return max(int(request.args.get("page", 1)), 1)
    except (TypeError, ValueError):
        return 1


def _page_info(has_next, page_size=30):
    page = _parse_page()
    return {
        "page": page,
        "has_prev": page > 1,
        "has_next": has_next,
        "page_size": page_size,
    }


def _pagination_url_builder():
    current_args = request.args.to_dict(flat=True)

    def build(page):
        args = dict(current_args)
        args["page"] = page
        return url_for(request.endpoint, **args)

    return build


def _to_decimal(value):
    if value is None:
        return None
    value = str(value).strip().replace(",", ".")
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _user_can(user, permission):
    if not user:
        return False
    if user.get("role") == "admin":
        return True
    return bool(user.get(permission))


def _require_permission(user, permission, redirect_endpoint="dashboard_bp.dashboard"):
    if _user_can(user, permission):
        return None
    flash("У вас нет доступа к этому разделу.", "danger")
    return redirect(url_for(redirect_endpoint))


def _log_action(request_id, action_type, user_id, old_status=None, new_status=None, note=None):
    execute_query(
        """
        INSERT INTO fuel_request_actions (
            request_id, action_type, old_status, new_status, action_by, note
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (request_id, action_type, old_status, new_status, user_id, note),
    )


def _all_active_companies():
    return fetch_all("SELECT id, name, is_internal FROM companies WHERE is_active = TRUE ORDER BY name")


def _base_request_query():
    return """
        SELECT
            fr.*,
            sc.name AS source_company_name,
            rc.name AS receiver_company_name,
            lc.name AS liability_company_name,
            fp.name AS source_fuel_point_name,
            fp.point_type AS source_point_type,
            v.plate_number,
            v.brand,
            vc.name AS vehicle_company_name,
            req_user.full_name AS requested_by_name,
            app_user.full_name AS approved_by_name,
            chk_user.full_name AS checked_by_name,
            tx.status AS fuel_tx_status
        FROM fuel_requests fr
        LEFT JOIN companies sc ON sc.id = fr.source_company_id
        LEFT JOIN companies rc ON rc.id = fr.receiver_company_id
        LEFT JOIN companies lc ON lc.id = fr.liability_company_id
        LEFT JOIN fuel_points fp ON fp.id = fr.source_fuel_point_id
        LEFT JOIN vehicles v ON v.id = fr.vehicle_id
        LEFT JOIN companies vc ON vc.id = v.company_id
        LEFT JOIN users req_user ON req_user.id = fr.requested_by
        LEFT JOIN users app_user ON app_user.id = fr.approved_by
        LEFT JOIN users chk_user ON chk_user.id = fr.checked_by
        LEFT JOIN fuel_transactions tx ON tx.id = fr.fuel_transaction_id
        WHERE 1=1
    """


def _approval_point_options(user):
    company_id, point_scope_id = get_scope_ids(user)
    sql = """
        SELECT fp.id, fp.name, fp.point_type, fp.company_id, c.name AS company_name
        FROM fuel_points fp
        LEFT JOIN companies c ON c.id = fp.company_id
        WHERE fp.is_active = TRUE
    """
    params = []

    if point_scope_id:
        sql += " AND fp.id = %s"
        params.append(point_scope_id)
    elif user.get("role") != "admin" and company_id:
        sql += " AND fp.company_id = %s"
        params.append(company_id)

    sql += " ORDER BY c.name, fp.name"
    return fetch_all(sql, tuple(params))


def _fetch_requests_for_user(user, mode="all", page=1, page_size=30):
    sql = _base_request_query()
    params = []
    company_id, point_scope_id = get_scope_ids(user)

    if user.get("role") != "admin":
        if mode == "mine":
            sql += " AND fr.requested_by = %s"
            params.append(user["id"])
        elif mode in ("approval", "fueling", "check"):
            sql += " AND fr.source_company_id = %s"
            params.append(company_id or -1)
        else:
            sql += " AND (fr.source_company_id = %s OR fr.receiver_company_id = %s OR fr.requested_by = %s OR fr.liability_company_id = %s)"
            params.extend([company_id or -1, company_id or -1, user["id"], company_id or -1])

    if point_scope_id:
        sql += " AND fr.source_fuel_point_id = %s"
        params.append(point_scope_id)

    if mode == "approval":
        sql += " AND fr.status = 'pending_approval'"
    elif mode == "fueling":
        sql += " AND fr.status = 'approved'"
    elif mode == "check":
        sql += " AND fr.status = 'fueling_done'"

    offset = (page - 1) * page_size
    sql += " ORDER BY fr.request_date DESC, fr.id DESC LIMIT %s OFFSET %s"
    params.extend([page_size + 1, offset])
    rows = fetch_all(sql, tuple(params))
    return rows[:page_size], len(rows) > page_size


def _fetch_request_by_id(request_id, user):
    sql = _base_request_query() + " AND fr.id = %s"
    params = [request_id]
    company_id, point_scope_id = get_scope_ids(user)
    if user.get("role") != "admin":
        sql += " AND (fr.source_company_id = %s OR fr.receiver_company_id = %s OR fr.requested_by = %s OR fr.liability_company_id = %s)"
        params.extend([company_id or -1, company_id or -1, user["id"], company_id or -1])
    if point_scope_id:
        sql += " AND fr.source_fuel_point_id = %s"
        params.append(point_scope_id)
    return fetch_one(sql, tuple(params))


def _request_form_context(user):
    companies = _all_active_companies()

    company_id = user.get("company_id") if user else None
    vehicle_sql = """
        SELECT v.id, v.plate_number, v.brand, v.vehicle_type, v.company_id, c.name AS company_name
        FROM vehicles v
        LEFT JOIN companies c ON c.id = v.company_id
        WHERE v.is_active = TRUE
    """
    vehicle_params = []
    if user and user.get("role") != "admin" and company_id:
        vehicle_sql += " AND v.company_id = %s"
        vehicle_params.append(company_id)
    vehicle_sql += " ORDER BY v.plate_number"
    vehicles = fetch_all(vehicle_sql, tuple(vehicle_params))

    user_company = None
    if company_id:
        user_company = fetch_one(
            "SELECT id, name, is_internal FROM companies WHERE id = %s",
            (company_id,),
        )

    return {
        "companies": companies,
        "vehicles": vehicles,
        "request_type_labels": REQUEST_TYPE_LABELS,
        "default_company_id": company_id,
        "user_company": user_company,
    }


@requests_bp.route("/requests")
@login_required
def requests_list():
    user = get_current_user()
    rows, has_next = _fetch_requests_for_user(user, mode="all", page=_parse_page())
    page_data = _page_info(has_next)
    return render_page(
        "requests_list.html",
        page_title="Реестр заявок",
        page_note="Все заявки, связанные с вашей компанией.",
        rows=rows,
        pagination=page_data,
        pagination_url=_pagination_url_builder(),
        request_type_labels=REQUEST_TYPE_LABELS,
        request_status_labels=REQUEST_STATUS_LABELS,
        list_mode="all",
        fuel_points=_approval_point_options(user),
        companies=_all_active_companies(),
    )


@requests_bp.route("/requests/my")
@login_required
def requests_my():
    user = get_current_user()
    denied = _require_permission(user, "can_request_create")
    if denied:
        return denied
    rows, has_next = _fetch_requests_for_user(user, mode="mine", page=_parse_page())
    page_data = _page_info(has_next)
    return render_page(
        "requests_list.html",
        page_title="Мои заявки",
        page_note="Заявки, созданные вами.",
        rows=rows,
        pagination=page_data,
        pagination_url=_pagination_url_builder(),
        request_type_labels=REQUEST_TYPE_LABELS,
        request_status_labels=REQUEST_STATUS_LABELS,
        list_mode="mine",
        fuel_points=_approval_point_options(user),
        companies=_all_active_companies(),
    )


@requests_bp.route("/requests/new", methods=["GET", "POST"])
@login_required
def requests_new():
    user = get_current_user()
    denied = _require_permission(user, "can_request_create")
    if denied:
        return denied

    if request.method == "POST":
        request_type = request.form.get("request_type", "").strip()
        needed_at_raw = request.form.get("needed_at") or None
        source_company_id = request.form.get("source_company_id") or None
        receiver_company_id = request.form.get("receiver_company_id") or None
        vehicle_id = request.form.get("vehicle_id") or None
        external_plate_number = request.form.get("external_plate_number", "").strip() or None
        driver_name = request.form.get("driver_name", "").strip() or None
        requested_liters = request.form.get("requested_liters") or 0
        requested_kg = 0
        purpose = request.form.get("purpose", "").strip() or None
        document_basis = request.form.get("document_basis", "").strip() or None
        document_number = request.form.get("document_number", "").strip() or None
        comment = request.form.get("comment", "").strip() or None

        if request_type not in REQUEST_TYPE_LABELS:
            flash("Выберите тип заявки.", "warning")
            return redirect(url_for("requests_bp.requests_new"))
        if not source_company_id or not receiver_company_id:
            flash("Укажите компанию-источник и компанию-получателя.", "warning")
            return redirect(url_for("requests_bp.requests_new"))
        if request_type == "external_vehicle_from_our_point" and not external_plate_number:
            flash("Для внешнего транспорта укажите госномер.", "warning")
            return redirect(url_for("requests_bp.requests_new"))
        if request_type == "our_vehicle_from_external_point" and not vehicle_id:
            flash("Для нашего транспорта выберите транспорт.", "warning")
            return redirect(url_for("requests_bp.requests_new"))

        source_company = fetch_one(
            "SELECT id, name FROM companies WHERE id = %s AND is_active = TRUE",
            (source_company_id,),
        )
        receiver_company = fetch_one(
            "SELECT id, name FROM companies WHERE id = %s AND is_active = TRUE",
            (receiver_company_id,),
        )
        if not source_company or not receiver_company:
            flash("Компания-источник или компания-получатель не найдены.", "danger")
            return redirect(url_for("requests_bp.requests_new"))

        if user.get("role") != "admin" and user.get("company_id"):
            if int(receiver_company_id) != int(user["company_id"]):
                flash(
                    "Обычный пользователь может создавать заявку только для своей компании / своего транспорта.",
                    "danger",
                )
                return redirect(url_for("requests_bp.requests_new"))

        vehicle_row = None
        if vehicle_id:
            vehicle_row = fetch_one(
                """
                SELECT v.id, v.company_id, v.plate_number, v.brand, c.name AS company_name
                FROM vehicles v
                LEFT JOIN companies c ON c.id = v.company_id
                WHERE v.id = %s AND v.is_active = TRUE
                """,
                (vehicle_id,),
            )
            if not vehicle_row:
                flash("Выбранный транспорт не найден.", "danger")
                return redirect(url_for("requests_bp.requests_new"))
            if int(vehicle_row.get("company_id") or 0) != int(receiver_company_id):
                flash("Выбранный транспорт должен принадлежать компании-получателю.", "danger")
                return redirect(url_for("requests_bp.requests_new"))

        needed_at = datetime.fromisoformat(needed_at_raw) if needed_at_raw else None

        row = execute_query_returning(
            """
            INSERT INTO fuel_requests (
                request_type, status, needed_at,
                source_company_id, receiver_company_id, source_fuel_point_id,
                vehicle_id, external_plate_number, driver_name,
                requested_liters, requested_kg,
                purpose, document_basis, document_number, comment,
                requested_by, updated_at
            )
            VALUES (
                %s, 'pending_approval', %s,
                %s, %s, NULL,
                %s, %s, %s,
                %s, %s,
                %s, %s, %s, %s,
                %s, CURRENT_TIMESTAMP
            )
            RETURNING id
            """,
            (
                request_type,
                needed_at,
                source_company_id,
                receiver_company_id,
                vehicle_id,
                external_plate_number,
                driver_name,
                requested_liters,
                requested_kg,
                purpose,
                document_basis,
                document_number,
                comment,
                user["id"],
            ),
        )
        _log_action(row["id"], "created", user["id"], None, "pending_approval", comment)
        flash(
            "Заявка создана. Теперь ответственная сторона должна назначить пункт топлива, согласованный объем и компанию, на которую относится топливо.",
            "success",
        )
        return redirect(url_for("requests_bp.requests_my"))

    return render_page("request_form.html", **_request_form_context(user))


@requests_bp.route("/requests/approval")
@login_required
def requests_approval():
    user = get_current_user()
    denied = _require_permission(user, "can_request_approve")
    if denied:
        return denied
    rows, has_next = _fetch_requests_for_user(user, mode="approval", page=_parse_page())
    page_data = _page_info(has_next)
    return render_page(
        "requests_list.html",
        page_title="Согласование заявок",
        page_note="Назначьте пункт топлива, согласуйте объем и укажите компанию, на которую относится отпущенное топливо.",
        rows=rows,
        pagination=page_data,
        pagination_url=_pagination_url_builder(),
        request_type_labels=REQUEST_TYPE_LABELS,
        request_status_labels=REQUEST_STATUS_LABELS,
        list_mode="approval",
        fuel_points=_approval_point_options(user),
        companies=_all_active_companies(),
    )


@requests_bp.route("/requests/<int:request_id>/approve", methods=["POST"])
@login_required
def request_approve(request_id):
    user = get_current_user()
    denied = _require_permission(user, "can_request_approve")
    if denied:
        return denied
    row = _fetch_request_by_id(request_id, user)
    if not row or row["status"] != "pending_approval":
        flash("Заявка недоступна для согласования.", "warning")
        return redirect(url_for("requests_bp.requests_approval"))
    if user.get("role") != "admin" and row.get("source_company_id") != user.get("company_id"):
        flash("Вы можете согласовывать только заявки своей компании-источника.", "danger")
        return redirect(url_for("requests_bp.requests_approval"))

    source_fuel_point_id = request.form.get("source_fuel_point_id") or row.get("source_fuel_point_id")
    if not source_fuel_point_id:
        flash("При согласовании обязательно укажите пункт топлива / объект отпуска.", "warning")
        return redirect(url_for("requests_bp.requests_approval"))

    point = fetch_one(
        """
        SELECT fp.id, fp.company_id, fp.name, c.name AS company_name
        FROM fuel_points fp
        LEFT JOIN companies c ON c.id = fp.company_id
        WHERE fp.id = %s AND fp.is_active = TRUE
        """,
        (source_fuel_point_id,),
    )
    if not point:
        flash("Выбранный пункт топлива не найден.", "danger")
        return redirect(url_for("requests_bp.requests_approval"))
    if row.get("source_company_id") and point.get("company_id") != row.get("source_company_id"):
        flash("Пункт топлива должен принадлежать компании-источнику заявки.", "danger")
        return redirect(url_for("requests_bp.requests_approval"))

    _, point_scope_id = get_scope_ids(user)
    if point_scope_id and point.get("id") != point_scope_id:
        flash("Вы можете работать только со своим закрепленным пунктом топлива.", "danger")
        return redirect(url_for("requests_bp.requests_approval"))

    liability_company_id = request.form.get("liability_company_id") or row.get("liability_company_id") or row.get("receiver_company_id")
    if not liability_company_id:
        flash("Укажите компанию, на которую относится отпущенное топливо.", "warning")
        return redirect(url_for("requests_bp.requests_approval"))

    liability_company = fetch_one(
        "SELECT id, name FROM companies WHERE id = %s AND is_active = TRUE",
        (liability_company_id,),
    )
    if not liability_company:
        flash("Выбранная компания для взаиморасчетов не найдена.", "danger")
        return redirect(url_for("requests_bp.requests_approval"))

    approved_liters = request.form.get("approved_liters") or row.get("requested_liters") or 0
    approved_kg = request.form.get("approved_kg") or row.get("requested_kg") or 0
    approval_note = (request.form.get("approve_note") or "").strip() or None

    execute_query(
        """
        UPDATE fuel_requests
        SET status = 'approved',
            source_fuel_point_id = %s,
            liability_company_id = %s,
            approved_liters = %s,
            approved_kg = %s,
            approval_note = %s,
            approved_by = %s,
            approved_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (source_fuel_point_id, liability_company_id, approved_liters, approved_kg, approval_note, user["id"], request_id),
    )
    _log_action(request_id, "approved", user["id"], "pending_approval", "approved", approval_note)

    loan_hint = ""
    if row.get("source_company_id") and int(row.get("source_company_id")) != int(liability_company_id):
        loan_hint = f" Отпуск будет отражен как выдача в долг компании {liability_company['name']}."

    flash(
        f"Заявка согласована. Топливо отнесено на компанию {liability_company['name']}.{loan_hint}",
        "success",
    )
    return redirect(url_for("requests_bp.requests_approval"))


@requests_bp.route("/requests/<int:request_id>/reject", methods=["POST"])
@login_required
def request_reject(request_id):
    user = get_current_user()
    denied = _require_permission(user, "can_request_approve")
    if denied:
        return denied
    row = _fetch_request_by_id(request_id, user)
    if not row or row["status"] != "pending_approval":
        flash("Заявка недоступна для отклонения.", "warning")
        return redirect(url_for("requests_bp.requests_approval"))
    if user.get("role") != "admin" and row.get("source_company_id") != user.get("company_id"):
        flash("Вы можете отклонять только заявки своей компании-источника.", "danger")
        return redirect(url_for("requests_bp.requests_approval"))

    note = (request.form.get("reject_note") or "").strip() or None
    execute_query(
        """
        UPDATE fuel_requests
        SET status = 'rejected',
            rejected_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (request_id,),
    )
    _log_action(request_id, "rejected", user["id"], "pending_approval", "rejected", note)
    flash("Заявка отклонена.", "info")
    return redirect(url_for("requests_bp.requests_approval"))


@requests_bp.route("/requests/fueling")
@login_required
def requests_fueling():
    user = get_current_user()
    if user.get("role") not in ("admin", "fuel_operator"):
        flash("У вас нет доступа к исполнению заявок.", "danger")
        return redirect(url_for("dashboard_bp.dashboard"))
    rows, has_next = _fetch_requests_for_user(user, mode="fueling", page=_parse_page())
    page_data = _page_info(has_next)
    return render_page(
        "requests_list.html",
        page_title="Исполнение заявок",
        page_note="Согласованные заявки, ожидающие фактической заправки.",
        rows=rows,
        pagination=page_data,
        pagination_url=_pagination_url_builder(),
        request_type_labels=REQUEST_TYPE_LABELS,
        request_status_labels=REQUEST_STATUS_LABELS,
        list_mode="fueling",
        default_density=DEFAULT_DENSITY,
        fuel_points=_approval_point_options(user),
        companies=_all_active_companies(),
    )


@requests_bp.route("/requests/<int:request_id>/fuel", methods=["POST"])
@login_required
def request_fuel(request_id):
    user = get_current_user()
    if user.get("role") not in ("admin", "fuel_operator"):
        flash("У вас нет доступа к исполнению заявок.", "danger")
        return redirect(url_for("dashboard_bp.dashboard"))

    row = _fetch_request_by_id(request_id, user)
    if not row or row["status"] != "approved":
        flash("Заявка недоступна для исполнения.", "warning")
        return redirect(url_for("requests_bp.requests_fueling"))
    _, point_scope_id = get_scope_ids(user)
    if user.get("role") != "admin" and row.get("source_company_id") != user.get("company_id"):
        flash("Вы можете исполнять только заявки своей компании-источника.", "danger")
        return redirect(url_for("requests_bp.requests_fueling"))
    if point_scope_id and row.get("source_fuel_point_id") != point_scope_id:
        flash("Вы можете исполнять заявки только своего пункта топлива.", "danger")
        return redirect(url_for("requests_bp.requests_fueling"))
    if not row.get("source_fuel_point_id"):
        flash("Сначала в заявке нужно назначить пункт топлива.", "warning")
        return redirect(url_for("requests_bp.requests_fueling"))

    actual_liters = _to_decimal(request.form.get("actual_liters")) or _to_decimal(row.get("approved_liters")) or _to_decimal(row.get("requested_liters")) or Decimal("0")
    actual_kg = _to_decimal(request.form.get("actual_kg")) or _to_decimal(row.get("approved_kg"))
    density = _to_decimal(request.form.get("density")) or _to_decimal(row.get("density")) or Decimal(str(DEFAULT_DENSITY))
    temperature = _to_decimal(request.form.get("temperature"))
    note = (request.form.get("fuel_note") or "").strip() or None

    if actual_liters <= 0:
        flash("Укажите фактический литраж.", "warning")
        return redirect(url_for("requests_bp.requests_fueling"))
    if actual_kg is None:
        actual_kg = actual_liters * density

    destination_name = None
    vehicle_id = row.get("vehicle_id")
    receiver_type = "vehicle" if vehicle_id else "other"
    if not vehicle_id:
        destination_name = " ".join(
            [part for part in [row.get("receiver_company_name"), row.get("external_plate_number")] if part]
        ) or row.get("external_plate_number")

    responsible_company_id = row.get("liability_company_id") or row.get("receiver_company_id")
    tx_comment = f"Исполнение заявки #{request_id}"
    if row.get("source_company_id") and responsible_company_id and int(row.get("source_company_id")) != int(responsible_company_id):
        tx_comment += f". Отпуск в долг компании {row.get('liability_company_name') or row.get('receiver_company_name') or ''}".rstrip()
    if note:
        tx_comment += f". {note}"

    tx = execute_query_returning(
        """
        INSERT INTO fuel_transactions (
            operation_date, fuel_point_id, operation_type, receiver_type,
            liters, kg, density, temperature,
            vehicle_id, destination_name,
            driver_name, task_basis, work_purpose,
            responsible_company_id, document_number, comment,
            entered_by, status
        )
        VALUES (
            CURRENT_TIMESTAMP, %s, 'EXPENSE', %s,
            %s, %s, %s, %s,
            %s, %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, 'pending'
        )
        RETURNING id
        """,
        (
            row.get("source_fuel_point_id"),
            receiver_type,
            str(actual_liters),
            str(actual_kg),
            str(density),
            str(temperature) if temperature is not None else None,
            vehicle_id,
            destination_name,
            row.get("driver_name"),
            row.get("document_basis"),
            row.get("purpose"),
            responsible_company_id,
            row.get("document_number"),
            tx_comment,
            user["id"],
        ),
    )

    execute_query(
        """
        UPDATE fuel_requests
        SET status = 'fueling_done',
            actual_liters = %s,
            actual_kg = %s,
            density = %s,
            temperature = %s,
            fuel_transaction_id = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (
            str(actual_liters),
            str(actual_kg),
            str(density),
            str(temperature) if temperature is not None else None,
            tx["id"],
            request_id,
        ),
    )
    _log_action(request_id, "fueling_done", user["id"], "approved", "fueling_done", note)
    flash("Заправка по заявке проведена. Движение топлива отражено в журнале и попадет в акт сверки после проверки.", "success")
    return redirect(url_for("requests_bp.requests_fueling"))


@requests_bp.route("/requests/check")
@login_required
def requests_check():
    user = get_current_user()
    denied = _require_permission(user, "can_request_check")
    if denied:
        return denied
    rows, has_next = _fetch_requests_for_user(user, mode="check", page=_parse_page())
    page_data = _page_info(has_next)
    return render_page(
        "requests_list.html",
        page_title="Проверка заявок",
        page_note="Заявки после фактической заправки, ожидающие проверки.",
        rows=rows,
        pagination=page_data,
        pagination_url=_pagination_url_builder(),
        request_type_labels=REQUEST_TYPE_LABELS,
        request_status_labels=REQUEST_STATUS_LABELS,
        list_mode="check",
        fuel_points=_approval_point_options(user),
        companies=_all_active_companies(),
    )


@requests_bp.route("/requests/<int:request_id>/check", methods=["POST"])
@login_required
def request_check(request_id):
    user = get_current_user()
    denied = _require_permission(user, "can_request_check")
    if denied:
        return denied
    row = _fetch_request_by_id(request_id, user)
    if not row or row["status"] != "fueling_done":
        flash("Заявка недоступна для проверки.", "warning")
        return redirect(url_for("requests_bp.requests_check"))
    if user.get("role") != "admin" and row.get("source_company_id") != user.get("company_id"):
        flash("Вы можете проверять только заявки своей компании-источника.", "danger")
        return redirect(url_for("requests_bp.requests_check"))

    note = (request.form.get("check_note") or "").strip() or None
    execute_query(
        """
        UPDATE fuel_requests
        SET status = 'checked',
            checked_by = %s,
            checked_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (user["id"], request_id),
    )
    if row.get("fuel_transaction_id"):
        execute_query(
            "UPDATE fuel_transactions SET status = 'approved' WHERE id = %s",
            (row["fuel_transaction_id"],),
        )
    _log_action(request_id, "checked", user["id"], "fueling_done", "checked", note)
    flash("Заявка проверена и закрыта.", "success")
    return redirect(url_for("requests_bp.requests_check"))
