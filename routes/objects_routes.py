from flask import Blueprint
from auth import login_required
from layout import render_page
from db import fetch_all

objects_bp = Blueprint("objects_bp", __name__)

@objects_bp.route("/objects")
@login_required
def objects_page():
    rows = fetch_all("""
        SELECT o.id, o.name, c.name AS company_name
        FROM objects o
        LEFT JOIN companies c ON c.id = o.company_id
        ORDER BY o.id DESC
    """)

    content = "<h2>Объекты</h2>"

    if rows:
        content += """
        <table border='1' cellpadding='8' cellspacing='0' style='border-collapse: collapse; width:100%;'>
            <tr>
                <th>ID</th>
                <th>Название объекта</th>
                <th>Компания</th>
            </tr>
        """
        for row in rows:
            content += f"""
            <tr>
                <td>{row['id']}</td>
                <td>{row['name']}</td>
                <td>{row['company_name'] or ''}</td>
            </tr>
            """
        content += "</table>"
    else:
        content += "<p>Объектов пока нет.</p>"

    return render_page("Объекты", content)
