from flask import Blueprint, redirect, url_for, flash
from db import fetch_all, execute_query
from auth import login_required, role_required, current_user
from layout import render_page

transactions_bp = Blueprint("transactions", __name__)


def is_admin_user(user):
    role = str((user or {}).get("role") or "").strip().lower()
    return role in ["admin", "администратор"]


@transactions_bp.route("/transactions")
@login_required
def transactions_page():
    user = current_user()
    is_admin = is_admin_user(user)
    company_id = user.get("company_id") if user else None
    user_id = user.get("id") if user else None

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
            ft.object_name,
            ft.fuel_station_id,
            fs.name AS fuel_station_name,
            fs.responsible_user_id AS station_responsible_user_id,
            o.company_id AS object_company_id,
            v.company_id AS vehicle_company_id
        FROM fuel_transactions ft
        LEFT JOIN fuel_stations fs
            ON fs.id = ft.fuel_station_id
        LEFT JOIN objects o
            ON o.name = ft.object_name
        LEFT JOIN vehicles v
            ON ft.vehicle ILIKE '%' || COALESCE(v.plate_number, '') || '%'
    """
    params = ()

    if not is_admin:
        filters = []
        values = []

        if company_id:
            filters.append("o.company_id = %s")
            values.append(company_id)

            filters.append("v.company_id = %s")
            values.append(company_id)

        if user_id:
            filters.append("fs.responsible_user_id = %s")
            values.append(user_id)

        if filters:
            query += " WHERE " + " OR ".join(filters)
            params = tuple(values)

    query += " ORDER BY ft.id DESC"

    transactions = fetch_all(query, params)

    rows = ""
    for t in transactions:
        entry_type_ru = "Приход" if t["entry_type"] == "kirim" else "Расход"

        rows += f"""
        <tr>
            <td>{t['id']}</td>
            <td>{t['object_name'] or ''}</td>
            <td>{t['fuel_station_name'] or ''}</td>
            <td>{t['vehicle'] or ''}</td>
            <td>{entry_type_ru}</td>
            <td>{t['liters']}</td>
            <td>{t['speedometer'] if t['speedometer'] is not None else ''}</td>
            <td>{t['entered_by'] or ''}</td>
            <td>{t['comment'] or ''}</td>
            <td>{t['created_at']}</td>
            <td>
                {"<a class='btn btn-delete' href='/transactions/delete/" + str(t["id"]) + "' onclick=\"return confirm('Удалить запись?')\">Удалить</a>" if is_admin else ""}
            </td>
        </tr>
        """

    if not rows:
        rows = """
        <tr>
            <td colspan="11" style="text-align:center; padding:20px;">
                Записи не найдены
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
                <th>Заправка</th>
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
