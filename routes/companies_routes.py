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
        rows += f"""
        <tr>
            <td>{c['id']}</td>
            <td>{c['name']}</td>
            <td style="display:flex; gap:5px;">
                <a href="/companies/edit/{c['id']}">
                    <button type="button">Изменить</button>
                </a>

                <form method="POST" action="/companies/delete/{c['id']}" 
                      onsubmit="return confirm('Удалить компанию?')">
                    <button type="submit" style="background:red;color:white;">
                        Удалить
                    </button>
                </form>
            </td>
        </tr>
        """

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
            <tr>
                <th>ID</th>
                <th>Название</th>
                <th>Действие</th>
            </tr>
            {rows}
        </table>
    </div>
    """

    return render_page("Компании", content)


# ✏️ EDIT
@companies_bp.route("/companies/edit/<int:company_id>", methods=["GET", "POST"])
@login_required
@role_required("admin")
def edit_company(company_id):
    company = fetch_one("SELECT * FROM companies WHERE id = %s", (company_id,))

    if not company:
        flash("Компания не найдена.", "error")
        return redirect("/companies")

    if request.method == "POST":
        name = request.form.get("name", "").strip()

        if not name:
            flash("Введите название компании.", "error")
            return redirect(f"/companies/edit/{company_id}")

        execute_query(
            "UPDATE companies SET name = %s WHERE id = %s",
            (name, company_id)
        )
        flash("Название компании обновлено.", "success")
        return redirect("/companies")

    content = f"""
    <div class="card">
        <h3>Изменить компанию</h3>
        <form method="POST">
            <input type="text" name="name" value="{company['name']}" required>
            <button type="submit">Сохранить</button>
            <a href="/companies">
                <button type="button">Назад</button>
            </a>
        </form>
    </div>
    """

    return render_page("Изменить компанию", content)


# 🗑 DELETE (SAFE - POST)
@companies_bp.route("/companies/delete/<int:company_id>", methods=["POST"])
@login_required
@role_required("admin")
def delete_company(company_id):
    company = fetch_one("SELECT * FROM companies WHERE id = %s", (company_id,))

    if not company:
        flash("Компания не найдена.", "error")
        return redirect("/companies")

    execute_query("DELETE FROM companies WHERE id = %s", (company_id,))
    flash("Компания удалена.", "success")

    return redirect("/companies")
