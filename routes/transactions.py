from flask import Blueprint, redirect, url_for, flash
from db import fetch_all, execute_query
from auth import login_required, role_required, current_user
from layout import render_page

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
            ft.vehicle,
            ft.object_name
        FROM fuel_transactions ft
    """
    params = ()

    # фильтр по компании (если нужно)
    if user["role"] != "admin" and user.get("company_id"):
        query += " WHERE ft.object_name IS NOT NULL "  # безопасный фильтр

    query += " ORDER BY ft.id DESC "

    transactions = fetch_all(query, params)

    rows = ""
    for t in transactions:
        entry_type_ru = "Приход" if t["entry_type"] == "kirim" else "Расход"

        rows += f"""
        <tr>
            <td>{t['id']}</td>
            <td>{t['object_name'] or ''}</td>
            <td>{t['vehicle'] or ''}</td>
            <td>{entry_type_ru}</td>
            <td>{t['liters']}</td>
            <td>{t['speedometer'] if t['speedometer'] is not None else ''}</td>
            <td>{t['entered_by'] or ''}</td>
            <td>{t['comment'] or ''}</td>
            <td>{t['created_at']}</td>
            <td>
                {"<a class='btn btn-delete' href='/transactions/delete/" + str(t["id"]) + "' onclick=\"return confirm('Удалить запись?')\">Удалить</a>" if user["role"] == "admin" else ""}
            </td>
        </tr>
        """

    content = f"""
    <div class="card">
        <h3>Журнал операций ГСМ</h3>
        <table>
            <tr>
                <th>ID</th>
                <th>Объект</th>
                <th>Транспорт</th>
                <th>Тип</th>
                <th>Литры</th>
                <th>Спидометр</th>
                <th>Кто ввел</th>
                <th>Комментарий</th>
                <th>Дата</th>
                <th>Действие</th>
            </tr>
            {rows}
        </table>
    </div>
    """

    return render_page("Журнал ГСМ", content)


@transactions_bp.route("/transactions/delete/<int:tx_id>")
@login_required
@role_required("admin")
def delete_transaction(tx_id):
    execute_query("DELETE FROM fuel_transactions WHERE id=%s", (tx_id,))
    flash("Запись удалена.", "success")
    return redirect(url_for("transactions.transactions_page"))
