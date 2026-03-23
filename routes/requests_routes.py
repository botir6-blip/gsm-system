from flask import Blueprint, request, redirect
from auth import login_required
from layout import render_page
from db import fetch_all, execute_query

# 🔴 МАНА ШУ ЙЎҚ ЭДИ
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
            r.status,
            r.created_at
        FROM fuel_requests r
        LEFT JOIN vehicles v ON v.id = r.vehicle_id
        LEFT JOIN objects o ON o.id = r.object_id
        ORDER BY r.id DESC
    """)

    content = "<h2>Заявки</h2>"

    if rows:
        content += """
        <table border='1' cellpadding='8' style='border-collapse: collapse; width:100%;'>
            <tr>
                <th>ID</th>
                <th>Транспорт</th>
                <th>Объект</th>
                <th>Запрошено (л)</th>
                <th>Фактически (л)</th>
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
                <td>{r['requested_liters']}</td>
                <td>{r['actual_liters'] or ''}</td>
                <td>{r['status']}</td>
                <td>{r['created_at']}</td>
            </tr>
            """
        content += "</table>"
    else:
        content += "<p>Заявок пока нет.</p>"

    content += "<br><a href='/requests/new'>➕ Новая заявка</a>"

    return render_page("Заявки", content)
