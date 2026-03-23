from flask import Blueprint, redirect, url_for
from db import fetch_all, execute_query
from auth import login_required, role_required, current_user
from app import render_page  # ⚠️ буни кейин тўғрилаймиз

transactions_bp = Blueprint("transactions", __name__)


@transactions_bp.route("/transactions")
@login_required
def transactions_page():
    user = current_user()

    query = """
        SELECT
            ft.id,
            ft.entry_type,
            ft.liters,
            ft.speedometer,
            ft.entered_by,
            ft.comment,
            ft.created_at,
            v.brand,
            v.vehicle_type,
            v.plate_number,
            o.name AS object_name
        FROM fuel_transactions ft
        LEFT JOIN vehicles v ON ft.vehicle_id = v.id
        LEFT JOIN objects o ON ft.object_id = o.id
    """
    params = ()

    if user["role"] != "admin" and user["company_id"]:
        query += " WHERE o.company_id = %s"
        params = (user["company_id"],)

    query += " ORDER BY ft.id DESC"

    transactions = fetch_all(query, params)

    rows = ""
    for t in transactions:
        entry_type_ru = "Приход" if t["entry_type"] == "kirim" else "Расход"
        rows += f"<tr><td>{t['id']}</td><td>{t['object_name']}</td><td>{t['liters']}</td></tr>"

    content = f"<table>{rows}</table>"

    return render_page("Журнал", content)


@transactions_bp.route("/transactions/delete/<int:tx_id>")
@login_required
@role_required("admin")
def delete_transaction(tx_id):
    execute_query("DELETE FROM fuel_transactions WHERE id=%s", (tx_id,))
    return redirect(url_for("transactions.transactions_page"))
