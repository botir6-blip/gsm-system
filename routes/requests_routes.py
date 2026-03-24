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
    role = (current_role() or "").lower()
    return role in ["администратор", "admin"]


def is_request_initiator():
    role = (current_role() or "").lower()
    return role in [
        "инициатор заявки",
        "initiator",
        "request_initiator",
        "dispatcher",
        "requester",
    ]


def is_internal_approver():
    role = (current_role() or "").lower()
    return role in [
        "согласующий по внутреннему транспорту",
        "internal_approver",
    ]


def is_external_approver():
    role = (current_role() or "").lower()
    return role in [
        "согласующий по стороннему транспорту",
        "external_approver",
    ]


def is_fuel_operator():
    role = (current_role() or "").lower()
    return role in [
        "оператор заправки",
        "fuel_operator",
        "operator",
        "fueler",
    ]


def is_controller():
    role = (current_role() or "").lower()
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


# ✅ ТУЗАТИЛГАН
def can_see_request_row(row):
    status = (row.get("status") or "").strip()
    approval_type = normalize_approval_type(row.get("approval_type"))

    if is_internal_approver():
        return status == "new" and approval_type == "internal"

    if is_external_approver():
        return status == "new" and approval_type == "external"

    if is_request_initiator():
        return status in ["new", "approved", "fueled", "driver_confirmed", "checked", "rejected"]

    if is_fuel_operator():
        return status in ["approved", "fueled"]

    if is_controller():
        return status in ["fueled", "driver_confirmed", "checked"]

    if is_admin():
        return True

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


# ✅ ЯНГИ
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
            r.status
        FROM fuel_requests r
        LEFT JOIN objects o ON o.id = r.object_id
        LEFT JOIN vehicles v ON v.id = r.vehicle_id
        ORDER BY r.id DESC
    """)

    visible_rows = [r for r in rows if can_see_request_row(r)]

    content = "<h2>Заявки</h2>"

    for r in visible_rows:
        transport = f"{r['plate_number'] or ''} {r['vehicle_name'] or ''}".strip()

        content += f"""
        <div style='border:1px solid #ddd; padding:10px; margin-bottom:10px;'>
            <b>ID:</b> {r['id']}<br>
            <b>Статус:</b> {status_label(r['status'])}<br>
            <small>{status_stage_label(r['status'])}</small><br>
            <b>Объект:</b> {r['object_name'] or '—'}<br>
            <b>Транспорт:</b> {transport or '—'}<br>
            <b>Литры:</b> {r['requested_liters'] or '—'}<br>
            <b>Подал:</b> {r['requested_by'] or '—'}<br>
            <a href='/requests/{r["id"]}'>Открыть</a>
        </div>
        """

    return render_page("Заявки", content)


@requests_bp.route("/requests/<int:request_id>/check", methods=["POST"])
@login_required
def request_check(request_id):
    req = fetch_one("""
        SELECT
            r.id,
            r.actual_liters,
            o.name AS object_name,
            v.plate_number,
            v.vehicle_name
        FROM fuel_requests r
        LEFT JOIN objects o ON o.id = r.object_id
        LEFT JOIN vehicles v ON v.id = r.vehicle_id
        WHERE r.id = %s
    """, (request_id,))

    controller_name = current_user_name()

    vehicle_text = f"{req['plate_number'] or ''} {req['vehicle_name'] or ''}".strip()

    execute_query("""
        UPDATE fuel_requests
        SET status = 'checked'
        WHERE id = %s
    """, (request_id,))

    execute_query("""
        INSERT INTO fuel_transactions (
            vehicle,
            object_name,
            liters,
            entered_by,
            dispatcher_status,
            entry_type
        )
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (
        vehicle_text,
        req["object_name"],
        req["actual_liters"] or 0,
        controller_name,
        "approved",
        "chiqim"
    ))

    return redirect("/requests")
