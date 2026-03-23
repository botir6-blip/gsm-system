from flask import Blueprint
from auth import login_required
from layout import render_page
from db import fetch_all

vehicles_bp = Blueprint("vehicles_bp", __name__)

@vehicles_bp.route("/vehicles")
@login_required
def vehicles_page():
    rows = fetch_all("""
        SELECT v.id, v.brand, v.vehicle_type, v.plate_number, c.name AS company_name
        FROM vehicles v
        LEFT JOIN companies c ON c.id = v.company_id
        ORDER BY v.id DESC
    """)

    content = "<h2>Транспорт</h2>"

    if rows:
        content += """
        <table border='1' cellpadding='8' cellspacing='0' style='border-collapse: collapse; width:100%;'>
            <tr>
                <th>ID</th>
                <th>Марка</th>
                <th>Тип</th>
                <th>Гос.номер</th>
                <th>Компания</th>
            </tr>
        """
        for row in rows:
            content += f"""
            <tr>
                <td>{row['id']}</td>
                <td>{row['brand']}</td>
                <td>{row['vehicle_type']}</td>
                <td>{row['plate_number']}</td>
                <td>{row['company_name'] or ''}</td>
            </tr>
            """
        content += "</table>"
    else:
        content += "<p>Транспорт пока не добавлен.</p>"

    return render_page("Транспорт", content)
