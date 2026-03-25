from flask import Blueprint, session
from auth import login_required
from layout import render_page
from db import fetch_all, fetch_one

transactions_bp = Blueprint("transactions_bp", __name__)


def get_current_user():
    return fetch_one("""
        SELECT id, full_name, role, company_id
        FROM users
        WHERE id = %s
    """, (session["user_id"],))


def get_status_badge(status):
    badges = {
        "fueled": "<span style='background:#dbeafe; color:#1d4ed8; padding:4px 8px; border-radius:8px; font-size:12px; font-weight:600;'>Заправлено</span>",
        "checked": "<span style='background:#dcfce7; color:#166534; padding:4px 8px; border-radius:8px; font-size:12px; font-weight:600;'>Проверено</span>",
        "closed": "<span style='background:#e5e7eb; color:#374151; padding:4px 8px; border-radius:8px; font-size:12px; font-weight:600;'>Завершена</span>",
    }
    return badges.get(status, status or "")


@transactions_bp.route("/transactions")
@login_required
def transactions_page():
    user = get_current_user()
    role = user["role"]
    company_id = user["company_id"]
    user_id = user["id"]

    base_sql = """
        SELECT
            fr.*,
            ru.full_name AS requester_name,
            fu.full_name AS fueler_name,
            cu.name AS requester_company_name,
            fp.name AS fuel_provider_company_name,
            o.name AS object_name,
            v.plate_number,
            v.vehicle_name,
            v.fuel_norm
        FROM fuel_requests fr
        LEFT JOIN users ru ON ru.id = fr.requester_user_id
        LEFT JOIN users fu ON fu.id = fr.fueled_by_user_id
        LEFT JOIN companies cu ON cu.id = fr.requester_company_id
        LEFT JOIN companies fp ON fp.id = fr.fuel_provider_company_id
        LEFT JOIN objects o ON o.id = fr.object_id
        LEFT JOIN vehicles v ON v.id = fr.vehicle_id
    """

    if role in ["admin"]:
        rows = fetch_all(base_sql + """
            WHERE fr.status IN ('fueled', 'checked', 'closed')
            ORDER BY fr.created_at DESC
        """)
    elif role in ["manager", "director", "deputy", "dispatcher", "ats_dispatcher"]:
        rows = fetch_all(base_sql + """
            WHERE fr.status IN ('fueled', 'checked', 'closed')
              AND (
                    fr.requester_company_id = %s
                    OR fr.fuel_provider_company_id = %s
                  )
            ORDER BY fr.created_at DESC
        """, (company_id, company_id))
    elif role in ["operator", "fuel_operator", "zapravka_operator"]:
        rows = fetch_all(base_sql + """
            WHERE fr.status IN ('fueled', 'checked', 'closed')
              AND fr.fueled_by_user_id = %s
            ORDER BY fr.created_at DESC
        """, (user_id,))
    else:
        rows = fetch_all(base_sql + """
            WHERE fr.status IN ('fueled', 'checked', 'closed')
              AND fr.requester_user_id = %s
            ORDER BY fr.created_at DESC
        """, (user_id,))

    html = """
    <h2>Журнал</h2>
    <div class="table-responsive">
    <table class="table table-bordered table-sm">
        <thead>
            <tr>
                <th>ID</th>
                <th>Дата</th>
                <th>Инициатор</th>
                <th>Компания</th>
                <th>Объект заправки</th>
                <th>Транспорт</th>
                <th>Норма расхода</th>
                <th>Запрошено</th>
                <th>Заправлено</th>
                <th>Поставщик топлива</th>
                <th>Статус</th>
            </tr>
        </thead>
        <tbody>
    """

    if not rows:
        html += """
            <tr>
                <td colspan="11" style="text-align:center; padding:20px;">
                    Журнал пока пуст
                </td>
            </tr>
        """
    else:
        for r in rows:
            transport_text = ""
            if r.get("plate_number"):
                transport_text = r["plate_number"]
                if r.get("vehicle_name"):
                    transport_text += f" | {r['vehicle_name']}"

            html += f"""
                <tr>
                    <td>{r['id']}</td>
                    <td>{r['created_at'].strftime('%Y-%m-%d %H:%M') if r['created_at'] else ''}</td>
                    <td>{r.get('requester_name') or ''}</td>
                    <td>{r.get('requester_company_name') or ''}</td>
                    <td>{r.get('object_name') or ''}</td>
                    <td>{transport_text}</td>
                    <td>{r.get('fuel_norm') or ''}</td>
                    <td>{r.get('requested_liters') or ''}</td>
                    <td>{r.get('fueled_liters') or ''}</td>
                    <td>{r.get('fuel_provider_company_name') or ''}</td>
                    <td>{get_status_badge(r.get('status'))}</td>
                </tr>
            """

    html += """
        </tbody>
    </table>
    </div>
    """

    return render_page("Журнал", html)
