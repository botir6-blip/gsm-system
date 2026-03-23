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
        return "Подтверждена"
    if status == "checked":
        return "Закрыта"
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
        <a href='/requests/new' style='text-decoration:none; padding:8px 12px; border:1px solid #ccc; border-radius:8px;'>
            ➕ Новая заявка
        </a>
    </div>
    """

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
                <th>Запрос</th>
                <th>За чей счет топливо</th>
                <th>Подал</th>
                <th>Действия</th>
            </tr>
        """

        for r in rows:
            transport = f"{r['plate_number'] or ''} {r['vehicle_name'] or ''}".strip()
            fact_text = f" / факт {r['actual_liters']} л" if r["actual_liters"] else ""
            approve_btn = ""

            if r["status"] == "new":
                approve_btn = f"""
                    <form method='post' action='/requests/{r["id"]}/approve' style='display:inline;'>
                        <button type='submit' style='padding:4px 8px; border:1px solid #1565c0; background:#1565c0; color:#fff; border-radius:6px; cursor:pointer;'>
                            Разрешить
                        </button>
                    </form>
                """

            content += f"""
            <tr>
                <td>{r['id']}</td>
                <td>
                    <span style='display:inline-block; padding:3px 8px; border-radius:999px; color:#fff; background:{status_color(r["status"])};'>
                        {status_label(r['status'])}
                    </span>
                </td>
                <td>{r['object_name'] or '—'}</td>
                <td>{transport or '—'}</td>
                <td>{r['requested_liters'] or '—'} л{fact_text}</td>
                <td>{r['fuel_supplier'] or '—'}</td>
                <td>{r['requested_by'] or '—'}</td>
                <td style='white-space:nowrap;'>
                    <a href='/requests/{r["id"]}' style='margin-right:8px;'>Подробнее</a>
                    {approve_btn}
                </td>
            </tr>
            """

        content += "</table></div>"
    else:
        content += "<p>Заявок пока нет.</p>"

    return render_page("Заявки", content)


@requests_bp.route("/requests/<int:request_id>")
@login_required
def request_detail(request_id):
    r = fetch_one("""
        SELECT
            r.*,
            o.name AS object_name,
            v.plate_number,
            v.vehicle_name
        FROM fuel_requests r
        LEFT JOIN objects o ON o.id = r.object_id
        LEFT JOIN vehicles v ON v.id = r.vehicle_id
        WHERE r.id = %s
    """, (request_id,))

    if not r:
        return render_page("Ошибка", "<p>Заявка не найдена.</p>")

    transport = f"{r['plate_number'] or ''} {r['vehicle_name'] or ''}".strip()

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
    </div>
    """

    return render_page(f"Заявка №{request_id}", content)


@requests_bp.route("/requests/<int:request_id>/approve", methods=["POST"])
@login_required
def approve_request(request_id):
    req = fetch_one("SELECT id, status FROM fuel_requests WHERE id = %s", (request_id,))
    if not req:
        return render_page("Ошибка", "<p>Заявка не найдена.</p>")

    if req["status"] != "new":
        return redirect("/requests")

    approver = current_user_name()

    execute_query("""
        UPDATE fuel_requests
        SET
            status = 'approved',
            approved_by = %s,
            approved_at = CURRENT_TIMESTAMP,
            approved_liters = COALESCE(approved_liters, requested_liters)
        WHERE id = %s
    """, (approver, request_id))

    return redirect("/requests")
