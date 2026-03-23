from functools import wraps
from flask import flash, redirect, session, url_for
from db import fetch_one


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None

    user = fetch_one("""
        SELECT u.*, c.name AS company_name
        FROM users u
        LEFT JOIN companies c ON u.company_id = c.id
        WHERE u.id = %s AND u.is_active = TRUE
    """, (user_id,))

    if not user:
        return None

    role_value = user.get("role")
    role_id = user.get("role_id")

    # Агар role матн бўлса, шу ҳолича ишлатамиз
    if role_value and not str(role_value).isdigit():
        user["role"] = str(role_value).strip()
        return user

    # Агар role_id алоҳида сақланган бўлса, roles жадвалидан номини оламиз
    lookup_role_id = role_id or role_value
    if lookup_role_id:
        role_row = fetch_one("""
            SELECT name
            FROM roles
            WHERE id = %s
        """, (lookup_role_id,))
        if role_row and role_row.get("name"):
            user["role"] = str(role_row["name"]).strip()

    return user


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user():
            flash("Сначала войдите в систему.", "error")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


def role_required(*roles):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user:
                flash("Сначала войдите в систему.", "error")
                return redirect(url_for("auth_bp.login"))
            if user["role"] not in roles:
                flash("У вас нет доступа к этому разделу.", "error")
                return redirect(url_for("index"))
            return fn(*args, **kwargs)
        return wrapper
    return decorator
