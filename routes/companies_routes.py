from flask import Blueprint, request, redirect, url_for, flash
from db import fetch_all, fetch_one, execute_query
from auth import login_required, role_required
from layout import render_page

companies_bp = Blueprint("companies_bp", __name__)

@companies_bp.route("/companies", methods=["GET", "POST"])
@login_required
@role_required("admin")
def companies_page():
    if request.method == "POST":
        name = request.form.get("name", "").strip()

        if not name:
            flash("Введите название компании.", "error")
            return redirect("/companies")

        execute_query("INSERT INTO companies (name) VALUES (%s)", (name,))
        flash("Компания добавлена.", "success")
        return redirect("/companies")

    companies = fetch_all("SELECT * FROM companies ORDER BY id DESC")

    rows = ""
    for c in companies:
        rows += f"<tr><td>{c['id']}</td><td>{c['name']}</td></tr>"

    content = f"""
    <div class="card">
        <h3>Добавить компанию</h3>
        <form method="POST">
            <input type="text" name="name" placeholder="Название компании" required>
            <button type="submit">Сохранить</button>
        </form>
    </div>

    <div class="card">
        <h3>Список компаний</h3>
        <table>
            <tr><th>ID</th><th>Название</th></tr>
            {rows}
        </table>
    </div>
    """

    return render_page("Компании", content)
