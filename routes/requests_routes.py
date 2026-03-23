from flask import Blueprint
from auth import login_required
from layout import render_page
from db import fetch_all

requests_bp = Blueprint("requests_bp", __name__)


@requests_bp.route("/requests")
@login_required
def requests_page():
    rows = fetch_all("""
        SELECT *
        FROM fuel_requests
        ORDER BY id DESC
    """)

    content = "<h2>Заявки</h2>"

    if rows:
        first_row = rows[0]

        content += "<table border='1' cellpadding='8' cellspacing='0' style='border-collapse: collapse; width:100%;'>"
        content += "<tr>"
        for key in first_row.keys():
            content += f"<th>{key}</th>"
        content += "</tr>"

        for row in rows:
            content += "<tr>"
            for key in first_row.keys():
                content += f"<td>{row[key]}</td>"
            content += "</tr>"
        content += "</table>"
    else:
        content += "<p>Заявок пока нет.</p>"

    content += "<br><a href='/requests/new'>➕ Новая заявка</a>"

    return render_page("Заявки", content)


@requests_bp.route("/requests/new")
@login_required
def new_request():
    return render_page("Новая заявка", "<h3>Форма заявки временно отключена</h3>")
