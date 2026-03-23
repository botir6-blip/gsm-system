from functools import wraps
from flask import flash, redirect, session, url_for
from db import fetch_one


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None

    return fetch_one("""
        SELECT u.*, c.name AS company_name
        FROM users u
        LEFT JOIN companies c ON u.company_id = c.id
        WHERE u.id = %s AND u.is_active = TRUE
    """, (user_id,))


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
                return redirect(url_for("login"))
            if user["role"] not in roles:
                flash("У вас нет доступа к этому разделу.", "error")
                return redirect(url_for("index"))
            return fn(*args, **kwargs)
        return wrapper
    return decorator
