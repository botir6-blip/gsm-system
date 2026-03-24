from flask import Blueprint
from auth import current_user, login_required
from db import fetch_one
from layout import render_page
from role_utils import get_role_name

dashboard_bp = Blueprint("dashboard_bp", __name__)

@dashboard_bp.route("/")
@login_required
def index():
    user = current_user()

    if user["role"] == "admin":
        company_count = fetch_one("SELECT COUNT(*) AS cnt FROM companies")["cnt"]
        object_count = fetch_one("SELECT COUNT(*) AS cnt FROM objects")["cnt"]
        vehicle_count = fetch_one("SELECT COUNT(*) AS cnt FROM vehicles")["cnt"]
        request_total = fetch_one("SELECT COUNT(*) AS cnt FROM fuel_requests")["cnt"]
        new_count = fetch_one("SELECT COUNT(*) AS cnt FROM fuel_requests WHERE status='new'")["cnt"]
        approved_count = fetch_one("SELECT COUNT(*) AS cnt FROM fuel_requests WHERE status='approved'")["cnt"]
        fueled_count = fetch_one("SELECT COUNT(*) AS cnt FROM fuel_requests WHERE status='fueled'")["cnt"]
        checked_count = fetch_one("SELECT COUNT(*) AS cnt FROM fuel_requests WHERE status='checked'")["cnt"]
    else:
        company_id = user["company_id"]
        company_count = 1 if company_id else 0
        object_count = fetch_one("SELECT COUNT(*) AS cnt FROM objects WHERE company_id=%s", (company_id,))["cnt"] if company_id else 0
        vehicle_count = fetch_one("SELECT COUNT(*) AS cnt FROM vehicles WHERE company_id=%s", (company_id,))["cnt"] if company_id else 0
        request_total = fetch_one("SELECT COUNT(*) AS cnt FROM fuel_requests WHERE requester_company_id=%s", (company_id,))["cnt"] if company_id else 0
        new_count = fetch_one("SELECT COUNT(*) AS cnt FROM fuel_requests WHERE requester_company_id=%s AND status='new'", (company_id,))["cnt"] if company_id else 0
        approved_count = fetch_one("SELECT COUNT(*) AS cnt FROM fuel_requests WHERE requester_company_id=%s AND status='approved'", (company_id,))["cnt"] if company_id else 0
        fueled_count = fetch_one("SELECT COUNT(*) AS cnt FROM fuel_requests WHERE requester_company_id=%s AND status='fueled'", (company_id,))["cnt"] if company_id else 0
        checked_count = fetch_one("SELECT COUNT(*) AS cnt FROM fuel_requests WHERE requester_company_id=%s AND status='checked'", (company_id,))["cnt"] if company_id else 0

    content = f"""
    <div class="dashboard">
        <div class="stat"><div class="label">Компании</div><div class="value">{company_count}</div></div>
        <div class="stat"><div class="label">Объекты</div><div class="value">{object_count}</div></div>
        <div class="stat"><div class="label">Транспорт</div><div class="value">{vehicle_count}</div></div>
        <div class="stat"><div class="label">Всего заявок</div><div class="value">{request_total}</div></div>
        <div class="stat"><div class="label">Новые</div><div class="value">{new_count}</div></div>
        <div class="stat"><div class="label">Разрешенные</div><div class="value">{approved_count}</div></div>
        <div class="stat"><div class="label">Заправленные</div><div class="value">{fueled_count}</div></div>
        <div class="stat"><div class="label">Проверенные</div><div class="value">{checked_count}</div></div>
    </div>

    <div class="grid-2">
        <div class="card">
            <h3>Ваш доступ</h3>
            <p><b>Роль:</b> {get_role_name(user['role'])}</p>
            <p><b>Пользователь:</b> {user['full_name']}</p>
            <p><b>Компания:</b> {user['company_name'] or '-'}</p>
        </div>
        <div class="card">
            <h3>Порядок работы</h3>
            <p>1. Инициатор заявки — создает заявку</p>
            <p>2. Согласующий — рассматривает заявку</p>
            <p>3. Оператор заправки — вводит фактическую заправку</p>
            <p>4. Контролёр — завершает проверку</p>
            <p>5. АТС-диспетчер — ведет транспорт</p>
        </div>
    </div>
    """
    return render_page("Панель управления ГСМ", content)
