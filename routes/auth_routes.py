from flask import Blueprint, request, redirect, url_for, flash, session
from werkzeug.security import check_password_hash

from db import fetch_one
from auth import current_user
from layout import render_page

auth_bp = Blueprint("auth_bp", __name__)

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("dashboard_bp.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        user = fetch_one("""
            SELECT *
            FROM users
            WHERE username = %s AND is_active = TRUE
        """, (username,))

        if not user or not check_password_hash(user["password_hash"], password):
            flash("Неверный логин или пароль.", "error")
            return redirect(url_for("auth_bp.login"))

        session["user_id"] = user["id"]
        flash("Вход выполнен.", "success")
        return redirect(url_for("dashboard_bp.index"))

    content = """
    <div class="card" style="max-width:520px; margin:auto;">
        <h3>Вход в систему</h3>
        <form method="POST">
            <input type="text" name="username" placeholder="Логин" required>
            <input type="password" name="password" placeholder="Пароль" required>
            <button type="submit">Войти</button>
        </form>
    </div>
    """
    return render_page("Вход", content)


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("Вы вышли из системы.", "success")
    return redirect(url_for("auth_bp.login"))
