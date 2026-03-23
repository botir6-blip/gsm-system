from flask import Blueprint
from auth import login_required
from layout import render_page

vehicles_bp = Blueprint("vehicles_bp", __name__)

@vehicles_bp.route("/vehicles")
@login_required
def vehicles_page():
    return render_page("Транспорт", "<h3>Транспорт пока не перенесен</h3>")
