from flask import Blueprint, request, redirect, url_for, flash
from werkzeug.security import generate_password_hash

from db import fetch_all, fetch_one, execute_query
from auth import login_required, role_required
from layout import render_page
from role_utils import get_role_name

users_bp = Blueprint("users_bp", __name__)

# =========================
# USERS
# =========================
@users_bp.route("/users", methods=["GET", "POST"])
@login_required
@role_required("admin")
def users_page():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        role = request.form.get("role", "").strip()
        company_id = request.form.get("company_id") or None

        if not full_name or not username or not password or not role:
            flash("Заполните обязательные поля.", "error")
            return redirect(url_for("users_bp.users_page"))

        existing = fetch_one("SELECT * FROM users WHERE username=%s", (username,))
        if existing:
            flash("Такой логин уже существует.", "error")
            return redirect(url_for("users_bp.users_page"))

        execute_query("""
            INSERT INTO users (full_name, username, password_hash, role, company_id, is_active)
            VALUES (%s, %s, %s, %s, %s, TRUE)
        """, (
            full_name,
            username,
            generate_password_hash(password),
            role,
            company_id
        ))

        flash("Пользователь создан.", "success")
        return redirect(url_for("users_bp.users_page"))

    companies = fetch_all("SELECT * FROM companies ORDER BY name")
    users = fetch_all("""
        SELECT u.*, c.name AS company_name
        FROM users u
        LEFT JOIN companies c ON u.company_id = c.id
        ORDER BY u.id DESC
    """)

    company_options = "".join(
        [f"<option value='{c['id']}'>{c['name']}</option>" for c in companies]
    )

    rows = ""
    for u in users:
        rows += f"""
        <tr>
            <td>{u['id']}</td>
            <td>{u['full_name']}</td>
            <td>{u['username']}</td>
            <td>{get_role_name(u['role'])}</td>
            <td>{u['company_name'] or ''}</td>
            <td>{"Да" if u['is_active'] else "Нет"}</td>
            <td>
                <div class="actions">
                    <a class="btn btn-edit" href="/users/edit/{u['id']}">Редактировать</a>
                </div>
            </td>
        </tr>
        """

    content = f"""
    <div class="card">
        <h3>Добавить пользователя</h3>
        <form method="POST">
            <input type="text" name="full_name" placeholder="ФИО" required>
            <input type="text" name="username" placeholder="Логин" required>
            <input type="password" name="password" placeholder="Пароль" required>
            <select name="role" required>
                <option value="">Выберите роль</option>
                <option value="admin">Администратор</option>
                <option value="requester">Инициатор заявки</option>
                <option value="internal_approver">Согласующий по внутреннему транспорту</option>
                <option value="external_approver">Согласующий по стороннему транспорту</option>
                <option value="fueler">Оператор заправки</option>
                <option value="controller">Контролёр</option>
                <option value="ats_operator">АТС-диспетчер</option>
            </select>
            <select name="company_id">
                <option value="">Компания (необязательно для admin)</option>
                {company_options}
            </select>
            <button type="submit">Сохранить</button>
        </form>
    </div>

    <div class="card">
        <h3>Пользователи</h3>
        <table>
            <tr>
                <th>ID</th>
                <th>ФИО</th>
                <th>Логин</th>
                <th>Роль</th>
                <th>Компания</th>
                <th>Активен</th>
                <th>Действия</th>
            </tr>
            {rows}
        </table>
    </div>
    """
    return render_page("Пользователи", content)


@users_bp.route("/users/edit/<int:user_id>", methods=["GET", "POST"])
@login_required
@role_required("admin")
def edit_user(user_id):
    user_row = fetch_one("SELECT * FROM users WHERE id=%s", (user_id,))
    if not user_row:
        flash("Пользователь не найден.", "error")
        return redirect(url_for("users_bp.users_page"))

    companies = fetch_all("SELECT * FROM companies ORDER BY name")

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        role = request.form.get("role", "").strip()
        company_id = request.form.get("company_id") or None
        is_active = True if request.form.get("is_active") == "on" else False

        if not full_name or not username or not role:
            flash("Заполните обязательные поля.", "error")
            return redirect(url_for("users_bp.edit_user", user_id=user_id))

        existing = fetch_one("SELECT * FROM users WHERE username=%s AND id<>%s", (username, user_id))
        if existing:
            flash("Другой пользователь с таким логином уже существует.", "error")
            return redirect(url_for("users_bp.edit_user", user_id=user_id))

        if password:
            execute_query("""
                UPDATE users
                SET full_name=%s, username=%s, password_hash=%s, role=%s, company_id=%s, is_active=%s
                WHERE id=%s
            """, (
                full_name, username, generate_password_hash(password), role, company_id, is_active, user_id
            ))
        else:
            execute_query("""
                UPDATE users
                SET full_name=%s, username=%s, role=%s, company_id=%s, is_active=%s
                WHERE id=%s
            """, (
                full_name, username, role, company_id, is_active, user_id
            ))

        flash("Пользователь обновлен.", "success")
        return redirect(url_for("users_bp.users_page"))

    company_options = "".join([
        f"<option value='{c['id']}' {'selected' if c['id'] == user_row['company_id'] else ''}>{c['name']}</option>"
        for c in companies
    ])

    checked = "checked" if user_row["is_active"] else ""

    content = f"""
    <div class="card">
        <h3>Редактирование пользователя</h3>
        <form method="POST">
            <input type="text" name="full_name" value="{user_row['full_name']}" required>
            <input type="text" name="username" value="{user_row['username']}" required>
            <input type="password" name="password" placeholder="Новый пароль (если нужно)">
            <select name="role" required>
                <option value="admin" {"selected" if user_row["role"]=="admin" else ""}>Администратор</option>
                <option value="requester" {"selected" if user_row["role"]=="requester" else ""}>Инициатор заявки</option>
                <option value="internal_approver" {"selected" if user_row["role"]=="internal_approver" else ""}>Согласующий по внутреннему транспорту</option>
                <option value="external_approver" {"selected" if user_row["role"]=="external_approver" else ""}>Согласующий по стороннему транспорту</option>
                <option value="fueler" {"selected" if user_row["role"]=="fueler" else ""}>Оператор заправки</option>
                <option value="controller" {"selected" if user_row["role"]=="controller" else ""}>Контролёр</option>
                <option value="ats_operator" {"selected" if user_row["role"]=="ats_operator" else ""}>АТС-диспетчер</option>
            </select>
            <select name="company_id">
                <option value="">Компания</option>
                {company_options}
            </select>
            <label><input type="checkbox" name="is_active" {checked}> Активен</label>
            <button type="submit">Сохранить изменения</button>
        </form>
        <br>
        <a class="btn btn-back" href="{url_for('users_page')}">Назад</a>
    </div>
    """
    return render_page("Редактирование пользователя", content)
