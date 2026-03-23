from flask import Blueprint
from auth import login_required
from layout import render_page

transactions_bp = Blueprint("transactions_bp", __name__)

@transactions_bp.route("/transactions")
@login_required
def transactions_page():
    return render_page("Журнал", "<h3>Журнал пока не перенесен</h3>")
