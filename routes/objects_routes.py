from flask import Blueprint
from auth import login_required
from layout import render_page

objects_bp = Blueprint("objects_bp", __name__)

@objects_bp.route("/objects")
@login_required
def objects_page():
    return render_page("Объекты", "<h3>Объекты пока не перенесены</h3>")
