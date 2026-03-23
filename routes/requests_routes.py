from flask import Blueprint
from auth import login_required
from layout import render_page

requests_bp = Blueprint("requests_bp", __name__)

@requests_bp.route("/requests")
@login_required
def requests_page():
    return render_page("Заявки", "<h3>Заявки пока не перенесены</h3>")


@requests_bp.route("/requests/new")
@login_required
def new_request():
    return render_page("Новая заявка", "<h3>Форма заявки будет тут</h3>")
