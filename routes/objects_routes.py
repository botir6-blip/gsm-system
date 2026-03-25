from flask import Blueprint, request, redirect, flash
from auth import login_required, role_required
from layout import render_page
from db import fetch_all, fetch_one, execute_query

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
                <th>Действие</th>
            </tr>
        """
        for row in rows:
            content += f"""
            <tr>
                <td>{row['id']}</td>
                <td>{row['name']}</td>
                <td>{row['company_name'] or ''}</td>
                <td style="display:flex; gap:5px;">
                    <a href="/objects/edit/{row['id']}">
                        <button type="button">Изменить</button>
                    </a>
                    <form method="POST" action="/objects/delete/{row['id']}" onsubmit="return confirm('Удалить объект?')">
                        <button type="submit" style="background:red;color:white;">Удалить</button>
                    </form>
                </td>
            </tr>
            """
        content += "</table>"
    else:
        content += "<p>Объектов пока нет.</p>"

    return render_page("Объекты", content)


@objects_bp.route("/objects/edit/<int:object_id>", methods=["GET", "POST"])
@login_required
@role_required("admin")
def edit_object(object_id):
    obj = fetch_one("SELECT * FROM objects WHERE id = %s", (object_id,))
    if not obj:
        flash("Объект не найден.", "error")
        return redirect("/objects")

    companies = fetch_all("SELECT id, name FROM companies ORDER BY name")

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        company_id = request.form.get("company_id", "").strip()

        if not name:
            flash("Введите название объекта.", "error")
            return redirect(f"/objects/edit/{object_id}")

        if company_id == "":
            company_id = None
        else:
            company_id = int(company_id)

        execute_query(
            "UPDATE objects SET name = %s, company_id = %s WHERE id = %s",
            (name, company_id, object_id)
        )
        flash("Объект обновлён.", "success")
        return redirect("/objects")

    company_options = "<option value=''>Без компании</option>"
    for c in companies:
        selected = "selected" if obj["company_id"] == c["id"] else ""
        company_options += f"<option value='{c['id']}' {selected}>{c['name']}</option>"

    content = f"""
    <div class="card">
        <h3>Изменить объект</h3>
        <form method="POST">
            <input type="text" name="name" value="{obj['name']}" placeholder="Название объекта" required>
            <select name="company_id">
                {company_options}
            </select>
            <button type="submit">Сохранить</button>
            <a href="/objects">
                <button type="button">Назад</button>
            </a>
        </form>
    </div>
    """

    return render_page("Изменить объект", content)


@objects_bp.route("/objects/delete/<int:object_id>", methods=["POST"])
@login_required
@role_required("admin")
def delete_object(object_id):
    obj = fetch_one("SELECT * FROM objects WHERE id = %s", (object_id,))
    if not obj:
        flash("Объект не найден.", "error")
        return redirect("/objects")

    execute_query("DELETE FROM objects WHERE id = %s", (object_id,))
    flash("Объект удалён.", "success")
    return redirect("/objects")
