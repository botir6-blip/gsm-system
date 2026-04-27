from datetime import datetime, date, time
from decimal import Decimal, InvalidOperation

from flask import Blueprint, request, redirect, url_for, flash

from auth import login_required, get_current_user, get_scope_ids
from db import DEFAULT_DENSITY, POINT_TYPE_LABELS, fetch_all, fetch_one, execute_query
from layout import render_page

reports_bp = Blueprint("reports_bp", __name__)

INCOMING_TYPES = ("INCOME", "TRANSFER_IN", "CORRECTION")
OUTGOING_TYPES = ("EXPENSE", "TRANSFER_OUT")
REQUEST_STATUS_LABELS = {
    "draft": "Черновик",
    "pending_approval": "Ожидает согласования",
    "approved": "Согласовано",
    "rejected": "Отклонено",
    "fueling_done": "Заправка выполнена",
    "checked": "Проверено",
    "cancelled": "Отменено",
}
OPERATION_LABELS = {
    "INCOME": "Приход",
    "EXPENSE": "Расход",
    "TRANSFER_IN": "Перемещение в пункт",
    "TRANSFER_OUT": "Перемещение из пункта",
    "CORRECTION": "Корректировка",
}


def _to_decimal(value):
    if value is None:
        return None
    value = str(value).strip().replace(",", ".")
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _default_period():
    today = date.today()
    start = today.replace(day=1)
    end = today
    return start.isoformat(), end.isoformat()


def _latest_opening_balance(fuel_point_id, op_dt):
    row = fetch_one(
        """
        SELECT balance_date, liters, kg, density
        FROM fuel_opening_balances
        WHERE fuel_point_id = %s AND balance_date <= %s
        ORDER BY balance_date DESC
        LIMIT 1
        """,
        (fuel_point_id, op_dt.date()),
    )
    if not row:
        return None
    liters = _to_decimal(row.get("liters")) or Decimal("0")
    density = _to_decimal(row.get("density")) or Decimal(str(DEFAULT_DENSITY))
    kg = _to_decimal(row.get("kg")) or (liters * density)
    return {"balance_date": row["balance_date"], "liters": liters, "kg": kg}


def _point_state_now(fuel_point_id, op_dt):
    opening = _latest_opening_balance(fuel_point_id, op_dt)
    liters = Decimal("0")
    kg = Decimal("0")
    params = [Decimal(str(DEFAULT_DENSITY)), Decimal(str(DEFAULT_DENSITY)), fuel_point_id]
    start_sql = ""
    if opening:
        liters = opening["liters"]
        kg = opening["kg"]
        start_sql = "AND operation_date >= %s"
        params.append(datetime.combine(opening["balance_date"], time.min))
    params.append(op_dt)

    delta = fetch_one(
        f"""
        SELECT
            COALESCE(SUM(
                CASE
                    WHEN operation_type IN ('INCOME','TRANSFER_IN','CORRECTION') AND status = 'approved' THEN liters
                    WHEN operation_type IN ('EXPENSE','TRANSFER_OUT') AND status <> 'rejected' THEN -liters
                    ELSE 0
                END
            ), 0) AS liters_delta,
            COALESCE(SUM(
                CASE
                    WHEN operation_type IN ('INCOME','TRANSFER_IN','CORRECTION') AND status = 'approved'
                        THEN COALESCE(NULLIF(kg, 0), liters * COALESCE(density, %s))
                    WHEN operation_type IN ('EXPENSE','TRANSFER_OUT') AND status <> 'rejected'
                        THEN -COALESCE(NULLIF(kg, 0), liters * COALESCE(density, %s))
                    ELSE 0
                END
            ), 0) AS kg_delta
        FROM fuel_transactions
        WHERE fuel_point_id = %s
          {start_sql}
          AND operation_date < %s
        """,
        tuple(params),
    )
    liters += _to_decimal(delta.get("liters_delta")) or Decimal("0")
    kg += _to_decimal(delta.get("kg_delta")) or Decimal("0")
    density = (kg / liters) if liters > 0 else Decimal(str(DEFAULT_DENSITY))
    return {"liters": liters, "kg": kg, "density": density}


def _company_options_for_user(user):
    company_id, _ = get_scope_ids(user)
    rows = fetch_all("SELECT id, name, is_internal FROM companies WHERE is_active = TRUE ORDER BY name")
    if user.get("role") == "admin":
        return rows
    if company_id:
        return rows
    return []


def _pair_allowed(user, lender_company_id, borrower_company_id):
    if user.get("role") == "admin":
        return True
    company_id, _ = get_scope_ids(user)
    if not company_id:
        return False
    return int(company_id) in {int(lender_company_id or 0), int(borrower_company_id or 0)}


def _month_start(raw_value=None):
    if raw_value:
        try:
            dt = datetime.strptime(raw_value, "%Y-%m")
            return dt.date().replace(day=1)
        except ValueError:
            pass
    today = date.today()
    return today.replace(day=1)


def _next_month(month_start):
    if month_start.month == 12:
        return date(month_start.year + 1, 1, 1)
    return date(month_start.year, month_start.month + 1, 1)


def _recon_redirect(lender_company_id, borrower_company_id, period_month):
    return redirect(
        url_for(
            "reports_bp.reconciliation_report",
            lender_company_id=lender_company_id,
            borrower_company_id=borrower_company_id,
            period_month=period_month,
        )
    )


def _reconciliation_opening(lender_company_id, borrower_company_id, period_start):
    row = fetch_one(
        """
        SELECT balance_date, liters, kg, comment
        FROM company_reconciliation_openings
        WHERE lender_company_id = %s
          AND borrower_company_id = %s
          AND balance_date <= %s
        ORDER BY balance_date DESC
        LIMIT 1
        """,
        (lender_company_id, borrower_company_id, period_start),
    )
    if not row:
        return {
            "balance_date": None,
            "liters": Decimal("0"),
            "kg": Decimal("0"),
            "comment": None,
        }
    liters = _to_decimal(row.get("liters")) or Decimal("0")
    kg = _to_decimal(row.get("kg")) or liters * Decimal(str(DEFAULT_DENSITY))
    return {
        "balance_date": row.get("balance_date"),
        "liters": liters,
        "kg": kg,
        "comment": row.get("comment"),
    }


def _reconciliation_movements(lender_company_id, borrower_company_id, period_start, period_end):
    row = fetch_one(
        """
        SELECT
            COALESCE(SUM(
                CASE
                    WHEN fp.company_id = %s AND ft.responsible_company_id = %s AND ft.operation_type IN ('EXPENSE', 'TRANSFER_OUT') THEN ft.liters
                    WHEN fp.company_id = %s AND ft.responsible_company_id = %s AND ft.operation_type IN ('INCOME', 'TRANSFER_IN', 'CORRECTION') THEN ft.liters
                    ELSE 0
                END
            ), 0) AS issued_liters,
            COALESCE(SUM(
                CASE
                    WHEN fp.company_id = %s AND ft.responsible_company_id = %s AND ft.operation_type IN ('EXPENSE', 'TRANSFER_OUT')
                        THEN COALESCE(NULLIF(ft.kg, 0), ft.liters * COALESCE(ft.density, %s))
                    WHEN fp.company_id = %s AND ft.responsible_company_id = %s AND ft.operation_type IN ('INCOME', 'TRANSFER_IN', 'CORRECTION')
                        THEN COALESCE(NULLIF(ft.kg, 0), ft.liters * COALESCE(ft.density, %s))
                    ELSE 0
                END
            ), 0) AS issued_kg,
            COALESCE(SUM(
                CASE
                    WHEN fp.company_id = %s AND ft.responsible_company_id = %s AND ft.operation_type IN ('INCOME', 'TRANSFER_IN', 'CORRECTION') THEN ft.liters
                    WHEN fp.company_id = %s AND ft.responsible_company_id = %s AND ft.operation_type IN ('EXPENSE', 'TRANSFER_OUT') THEN ft.liters
                    ELSE 0
                END
            ), 0) AS returned_liters,
            COALESCE(SUM(
                CASE
                    WHEN fp.company_id = %s AND ft.responsible_company_id = %s AND ft.operation_type IN ('INCOME', 'TRANSFER_IN', 'CORRECTION')
                        THEN COALESCE(NULLIF(ft.kg, 0), ft.liters * COALESCE(ft.density, %s))
                    WHEN fp.company_id = %s AND ft.responsible_company_id = %s AND ft.operation_type IN ('EXPENSE', 'TRANSFER_OUT')
                        THEN COALESCE(NULLIF(ft.kg, 0), ft.liters * COALESCE(ft.density, %s))
                    ELSE 0
                END
            ), 0) AS returned_kg
        FROM fuel_transactions ft
        LEFT JOIN fuel_points fp ON fp.id = ft.fuel_point_id
        WHERE ft.status = 'approved'
          AND ft.operation_date >= %s
          AND ft.operation_date < %s
          AND ft.operation_type IN ('INCOME', 'TRANSFER_IN', 'CORRECTION', 'EXPENSE', 'TRANSFER_OUT')
          AND (
                (fp.company_id = %s AND ft.responsible_company_id = %s)
             OR (fp.company_id = %s AND ft.responsible_company_id = %s)
          )
        """,
        (
            lender_company_id,
            borrower_company_id,
            borrower_company_id,
            lender_company_id,
            lender_company_id,
            borrower_company_id,
            DEFAULT_DENSITY,
            borrower_company_id,
            lender_company_id,
            DEFAULT_DENSITY,
            lender_company_id,
            borrower_company_id,
            borrower_company_id,
            lender_company_id,
            lender_company_id,
            borrower_company_id,
            DEFAULT_DENSITY,
            borrower_company_id,
            lender_company_id,
            DEFAULT_DENSITY,
            period_start,
            period_end,
            lender_company_id,
            borrower_company_id,
            borrower_company_id,
            lender_company_id,
        ),
    ) or {}
    return {
        "issued_liters": _to_decimal(row.get("issued_liters")) or Decimal("0"),
        "issued_kg": _to_decimal(row.get("issued_kg")) or Decimal("0"),
        "returned_liters": _to_decimal(row.get("returned_liters")) or Decimal("0"),
        "returned_kg": _to_decimal(row.get("returned_kg")) or Decimal("0"),
    }


def _reconciliation_details(lender_company_id, borrower_company_id, period_start, period_end):
    rows = fetch_all(
        """
        SELECT
            ft.id,
            ft.operation_date,
            ft.operation_type,
            ft.liters,
            COALESCE(NULLIF(ft.kg, 0), ft.liters * COALESCE(ft.density, %s)) AS kg_effective,
            ft.document_number,
            ft.comment,
            fp.name AS fuel_point_name,
            fp.company_id AS source_company_id,
            sc.name AS source_company_name,
            rc.name AS responsible_company_name,
            fr.id AS request_id,
            CASE
                WHEN (
                    (fp.company_id = %s AND ft.responsible_company_id = %s AND ft.operation_type IN ('EXPENSE', 'TRANSFER_OUT'))
                    OR
                    (fp.company_id = %s AND ft.responsible_company_id = %s AND ft.operation_type IN ('INCOME', 'TRANSFER_IN', 'CORRECTION'))
                ) THEN 'issued'
                ELSE 'returned'
            END AS direction
        FROM fuel_transactions ft
        LEFT JOIN fuel_points fp ON fp.id = ft.fuel_point_id
        LEFT JOIN companies sc ON sc.id = fp.company_id
        LEFT JOIN companies rc ON rc.id = ft.responsible_company_id
        LEFT JOIN fuel_requests fr ON fr.fuel_transaction_id = ft.id
        WHERE ft.status = 'approved'
          AND ft.operation_date >= %s
          AND ft.operation_date < %s
          AND ft.operation_type IN ('INCOME', 'TRANSFER_IN', 'CORRECTION', 'EXPENSE', 'TRANSFER_OUT')
          AND (
                (fp.company_id = %s AND ft.responsible_company_id = %s)
             OR (fp.company_id = %s AND ft.responsible_company_id = %s)
          )
        ORDER BY ft.operation_date DESC, ft.id DESC
        """,
        (
            DEFAULT_DENSITY,
            lender_company_id,
            borrower_company_id,
            borrower_company_id,
            lender_company_id,
            period_start,
            period_end,
            lender_company_id,
            borrower_company_id,
            borrower_company_id,
            lender_company_id,
        ),
    )
    for row in rows:
        row["direction_label"] = "Выдано в долг" if row["direction"] == "issued" else "Погашение встречным отпуском"
    return rows


@reports_bp.route('/reports')
@login_required
def reports():
    user = get_current_user()
    company_id, point_scope_id = get_scope_ids(user)

    date_from = request.args.get('date_from') or _default_period()[0]
    date_to = request.args.get('date_to') or _default_period()[1]
    filter_point_id = request.args.get('point_id') or ''
    if point_scope_id:
        filter_point_id = str(point_scope_id)

    points_sql = "SELECT id, name, point_type FROM fuel_points WHERE is_active = TRUE"
    points_params = []
    if point_scope_id:
        points_sql += " AND id = %s"
        points_params.append(point_scope_id)
    elif company_id:
        points_sql += " AND company_id = %s"
        points_params.append(company_id)
    points_sql += " ORDER BY point_type, name"
    scoped_points = fetch_all(points_sql, tuple(points_params))

    summary_sql = """
        SELECT
            COALESCE(SUM(CASE WHEN ft.operation_type IN %s AND ft.status = 'approved' THEN ft.liters ELSE 0 END), 0) AS income_liters,
            COALESCE(SUM(CASE WHEN ft.operation_type IN %s AND ft.status = 'approved' THEN COALESCE(NULLIF(ft.kg, 0), ft.liters * COALESCE(ft.density, %s)) ELSE 0 END), 0) AS income_kg,
            COALESCE(SUM(CASE WHEN ft.operation_type IN %s AND ft.status <> 'rejected' THEN ft.liters ELSE 0 END), 0) AS expense_liters,
            COALESCE(SUM(CASE WHEN ft.operation_type IN %s AND ft.status <> 'rejected' THEN COALESCE(NULLIF(ft.kg, 0), ft.liters * COALESCE(ft.density, %s)) ELSE 0 END), 0) AS expense_kg,
            COUNT(*) AS operation_count
        FROM fuel_transactions ft
        LEFT JOIN fuel_points fp ON fp.id = ft.fuel_point_id
        WHERE ft.operation_date >= %s
          AND ft.operation_date < (%s::date + INTERVAL '1 day')
    """
    summary_params = [tuple(INCOMING_TYPES), tuple(INCOMING_TYPES), DEFAULT_DENSITY, tuple(OUTGOING_TYPES), tuple(OUTGOING_TYPES), DEFAULT_DENSITY, date_from, date_to]
    if filter_point_id:
        summary_sql += " AND ft.fuel_point_id = %s"
        summary_params.append(filter_point_id)
    elif company_id:
        summary_sql += " AND fp.company_id = %s"
        summary_params.append(company_id)
    summary = fetch_one(summary_sql, tuple(summary_params)) or {}

    current_balance_liters = Decimal('0')
    current_balance_kg = Decimal('0')
    point_balance_rows = []
    for point in scoped_points:
        if filter_point_id and str(point['id']) != str(filter_point_id):
            continue
        mov_sql = """
            SELECT
                COALESCE(SUM(CASE WHEN operation_type IN %s AND status = 'approved' THEN liters ELSE 0 END), 0) AS in_liters,
                COALESCE(SUM(CASE WHEN operation_type IN %s AND status = 'approved' THEN COALESCE(NULLIF(kg, 0), liters * COALESCE(density, %s)) ELSE 0 END), 0) AS in_kg,
                COALESCE(SUM(CASE WHEN operation_type IN %s AND status <> 'rejected' THEN liters ELSE 0 END), 0) AS out_liters,
                COALESCE(SUM(CASE WHEN operation_type IN %s AND status <> 'rejected' THEN COALESCE(NULLIF(kg, 0), liters * COALESCE(density, %s)) ELSE 0 END), 0) AS out_kg
            FROM fuel_transactions
            WHERE fuel_point_id = %s
              AND operation_date >= %s
              AND operation_date < (%s::date + INTERVAL '1 day')
        """
        mov = fetch_one(mov_sql, (tuple(INCOMING_TYPES), tuple(INCOMING_TYPES), DEFAULT_DENSITY, tuple(OUTGOING_TYPES), tuple(OUTGOING_TYPES), DEFAULT_DENSITY, point['id'], date_from, date_to)) or {}
        state = _point_state_now(point['id'], datetime(2100, 1, 1, 0, 0, 0))
        current_balance_liters += state['liters']
        current_balance_kg += state['kg']
        point_balance_rows.append({
            'id': point['id'],
            'name': point['name'],
            'point_type': point['point_type'],
            'point_type_label': POINT_TYPE_LABELS.get(point['point_type'], point['point_type']),
            'in_liters': float(_to_decimal(mov.get('in_liters')) or Decimal('0')),
            'in_kg': float(_to_decimal(mov.get('in_kg')) or Decimal('0')),
            'out_liters': float(_to_decimal(mov.get('out_liters')) or Decimal('0')),
            'out_kg': float(_to_decimal(mov.get('out_kg')) or Decimal('0')),
            'balance_liters': float(state['liters']),
            'balance_kg': float(state['kg']),
            'avg_density': float(state['density']),
        })

    current_density = (current_balance_kg / current_balance_liters) if current_balance_liters > 0 else Decimal(str(DEFAULT_DENSITY))

    transport_sql = """
        SELECT
            v.id,
            v.plate_number,
            v.brand,
            v.vehicle_type,
            COUNT(ft.id) AS operation_count,
            COALESCE(SUM(ft.liters), 0) AS liters,
            COALESCE(SUM(COALESCE(NULLIF(ft.kg, 0), ft.liters * COALESCE(ft.density, %s))), 0) AS kg
        FROM fuel_transactions ft
        LEFT JOIN vehicles v ON v.id = ft.vehicle_id
        LEFT JOIN fuel_points fp ON fp.id = ft.fuel_point_id
        WHERE ft.receiver_type = 'vehicle'
          AND ft.operation_type = 'EXPENSE'
          AND ft.status <> 'rejected'
          AND ft.operation_date >= %s
          AND ft.operation_date < (%s::date + INTERVAL '1 day')
    """
    transport_params = [DEFAULT_DENSITY, date_from, date_to]
    if filter_point_id:
        transport_sql += " AND ft.fuel_point_id = %s"
        transport_params.append(filter_point_id)
    elif company_id:
        transport_sql += " AND fp.company_id = %s"
        transport_params.append(company_id)
    transport_sql += " GROUP BY v.id, v.plate_number, v.brand, v.vehicle_type ORDER BY liters DESC, v.plate_number"
    transport_rows = fetch_all(transport_sql, tuple(transport_params))

    req_sql = """
        SELECT fr.status, COUNT(*) AS request_count,
               COALESCE(SUM(fr.requested_liters), 0) AS requested_liters,
               COALESCE(SUM(fr.actual_liters), 0) AS actual_liters
        FROM fuel_requests fr
        LEFT JOIN fuel_points fp ON fp.id = fr.source_fuel_point_id
        WHERE fr.request_date >= %s
          AND fr.request_date < (%s::date + INTERVAL '1 day')
    """
    req_params = [date_from, date_to]
    if filter_point_id:
        req_sql += " AND fr.source_fuel_point_id = %s"
        req_params.append(filter_point_id)
    elif company_id:
        req_sql += " AND fp.company_id = %s"
        req_params.append(company_id)
    req_sql += " GROUP BY fr.status ORDER BY fr.status"
    request_rows = fetch_all(req_sql, tuple(req_params))
    for row in request_rows:
        row['status_label'] = REQUEST_STATUS_LABELS.get(row['status'], row['status'])

    summary_cards = {
        'income_liters': float(_to_decimal(summary.get('income_liters')) or Decimal('0')),
        'income_kg': float(_to_decimal(summary.get('income_kg')) or Decimal('0')),
        'expense_liters': float(_to_decimal(summary.get('expense_liters')) or Decimal('0')),
        'expense_kg': float(_to_decimal(summary.get('expense_kg')) or Decimal('0')),
        'operation_count': summary.get('operation_count') or 0,
        'current_balance_liters': float(current_balance_liters),
        'current_balance_kg': float(current_balance_kg),
        'current_balance_density': float(current_density),
    }

    return render_page(
        'reports.html',
        summary=summary_cards,
        point_rows=point_balance_rows,
        transport_rows=transport_rows,
        request_rows=request_rows,
        scoped_points=scoped_points,
        filters={'date_from': date_from, 'date_to': date_to, 'point_id': str(filter_point_id) if filter_point_id else ''},
        point_type_labels=POINT_TYPE_LABELS,
        request_status_labels=REQUEST_STATUS_LABELS,
    )


@reports_bp.route('/reports/reconciliation')
@login_required
def reconciliation_report():
    user = get_current_user()
    companies = _company_options_for_user(user)
    company_id, _ = get_scope_ids(user)

    lender_company_id = request.args.get('lender_company_id') or (str(company_id) if company_id else '')
    borrower_company_id = request.args.get('borrower_company_id') or ''
    period_start = _month_start(request.args.get('period_month'))
    period_end = _next_month(period_start)
    period_month = period_start.strftime('%Y-%m')

    lender_company = fetch_one('SELECT id, name FROM companies WHERE id = %s', (lender_company_id,)) if lender_company_id else None
    borrower_company = fetch_one('SELECT id, name FROM companies WHERE id = %s', (borrower_company_id,)) if borrower_company_id else None

    summary = None
    detail_rows = []
    opening_rows = []
    recent_acts = []
    saved_act = None

    if lender_company_id and borrower_company_id:
        if lender_company_id == borrower_company_id:
            flash('Для акта сверки выберите две разные компании.', 'warning')
        elif not _pair_allowed(user, lender_company_id, borrower_company_id):
            flash('У вас нет доступа к этой паре компаний.', 'danger')
        else:
            opening = _reconciliation_opening(lender_company_id, borrower_company_id, period_start)
            moves = _reconciliation_movements(lender_company_id, borrower_company_id, period_start, period_end)
            closing_liters = opening['liters'] + moves['issued_liters'] - moves['returned_liters']
            closing_kg = opening['kg'] + moves['issued_kg'] - moves['returned_kg']
            summary = {
                'opening_liters': float(opening['liters']),
                'opening_kg': float(opening['kg']),
                'issued_liters': float(moves['issued_liters']),
                'issued_kg': float(moves['issued_kg']),
                'returned_liters': float(moves['returned_liters']),
                'returned_kg': float(moves['returned_kg']),
                'closing_liters': float(closing_liters),
                'closing_kg': float(closing_kg),
                'opening_date': opening.get('balance_date'),
                'opening_comment': opening.get('comment'),
            }
            detail_rows = _reconciliation_details(lender_company_id, borrower_company_id, period_start, period_end)
            opening_rows = fetch_all(
                """
                SELECT o.*, lc.name AS lender_company_name, bc.name AS borrower_company_name, u.full_name AS created_by_name
                FROM company_reconciliation_openings o
                LEFT JOIN companies lc ON lc.id = o.lender_company_id
                LEFT JOIN companies bc ON bc.id = o.borrower_company_id
                LEFT JOIN users u ON u.id = o.created_by
                WHERE o.lender_company_id = %s AND o.borrower_company_id = %s
                ORDER BY o.balance_date DESC
                """,
                (lender_company_id, borrower_company_id),
            )
            saved_act = fetch_one(
                """
                SELECT a.*, lc.name AS lender_company_name, bc.name AS borrower_company_name, u.full_name AS created_by_name
                FROM company_reconciliation_acts a
                LEFT JOIN companies lc ON lc.id = a.lender_company_id
                LEFT JOIN companies bc ON bc.id = a.borrower_company_id
                LEFT JOIN users u ON u.id = a.created_by
                WHERE a.lender_company_id = %s AND a.borrower_company_id = %s AND a.period_month = %s
                LIMIT 1
                """,
                (lender_company_id, borrower_company_id, period_start),
            )

    acts_sql = """
        SELECT a.*, lc.name AS lender_company_name, bc.name AS borrower_company_name, u.full_name AS created_by_name
        FROM company_reconciliation_acts a
        LEFT JOIN companies lc ON lc.id = a.lender_company_id
        LEFT JOIN companies bc ON bc.id = a.borrower_company_id
        LEFT JOIN users u ON u.id = a.created_by
        WHERE 1=1
    """
    acts_params = []
    if user.get('role') != 'admin' and company_id:
        acts_sql += ' AND (a.lender_company_id = %s OR a.borrower_company_id = %s)'
        acts_params.extend([company_id, company_id])
    acts_sql += ' ORDER BY a.period_month DESC, a.id DESC LIMIT 50'
    recent_acts = fetch_all(acts_sql, tuple(acts_params))

    return render_page(
        'reconciliation.html',
        companies=companies,
        lender_company=lender_company,
        borrower_company=borrower_company,
        filters={
            'lender_company_id': str(lender_company_id) if lender_company_id else '',
            'borrower_company_id': str(borrower_company_id) if borrower_company_id else '',
            'period_month': period_month,
        },
        summary=summary,
        detail_rows=detail_rows,
        opening_rows=opening_rows,
        recent_acts=recent_acts,
        saved_act=saved_act,
        default_opening_date='2026-04-01',
    )


@reports_bp.route('/reports/reconciliation/opening', methods=['POST'])
@login_required
def reconciliation_save_opening():
    user = get_current_user()
    lender_company_id = request.form.get('lender_company_id') or ''
    borrower_company_id = request.form.get('borrower_company_id') or ''
    balance_date = request.form.get('balance_date') or ''
    liters = _to_decimal(request.form.get('liters'))
    kg = _to_decimal(request.form.get('kg'))
    comment = (request.form.get('comment') or '').strip() or None

    period_month = request.form.get('period_month') or _month_start().strftime('%Y-%m')

    if not lender_company_id or not borrower_company_id or not balance_date or liters is None:
        flash('Для ввода остатка укажите две компании, дату и литры.', 'warning')
        return _recon_redirect(lender_company_id, borrower_company_id, period_month)
    if lender_company_id == borrower_company_id:
        flash('Для остатка выберите две разные компании.', 'warning')
        return _recon_redirect(lender_company_id, borrower_company_id, period_month)
    if not _pair_allowed(user, lender_company_id, borrower_company_id):
        flash('У вас нет доступа к этой паре компаний.', 'danger')
        return _recon_redirect(lender_company_id, borrower_company_id, period_month)

    if kg is None:
        kg = liters * Decimal(str(DEFAULT_DENSITY))

    execute_query(
        """
        INSERT INTO company_reconciliation_openings (
            lender_company_id, borrower_company_id, balance_date, liters, kg, comment, created_by
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (lender_company_id, borrower_company_id, balance_date)
        DO UPDATE SET
            liters = EXCLUDED.liters,
            kg = EXCLUDED.kg,
            comment = EXCLUDED.comment,
            created_by = EXCLUDED.created_by,
            created_at = CURRENT_TIMESTAMP
        """,
        (lender_company_id, borrower_company_id, balance_date, str(liters), str(kg), comment, user['id']),
    )
    flash('Начальный остаток по акту сверки сохранен.', 'success')
    return _recon_redirect(lender_company_id, borrower_company_id, period_month)


@reports_bp.route('/reports/reconciliation/save-act', methods=['POST'])
@login_required
def reconciliation_save_act():
    user = get_current_user()
    lender_company_id = request.form.get('lender_company_id') or ''
    borrower_company_id = request.form.get('borrower_company_id') or ''
    period_month = request.form.get('period_month') or _month_start().strftime('%Y-%m')
    act_number = (request.form.get('act_number') or '').strip() or None
    act_date = request.form.get('act_date') or None
    note = (request.form.get('note') or '').strip() or None

    if not lender_company_id or not borrower_company_id:
        flash('Сначала выберите пару компаний.', 'warning')
        return _recon_redirect(lender_company_id, borrower_company_id, period_month)
    if lender_company_id == borrower_company_id:
        flash('Для акта сверки выберите две разные компании.', 'warning')
        return _recon_redirect(lender_company_id, borrower_company_id, period_month)
    if not _pair_allowed(user, lender_company_id, borrower_company_id):
        flash('У вас нет доступа к этой паре компаний.', 'danger')
        return _recon_redirect(lender_company_id, borrower_company_id, period_month)

    period_start = _month_start(period_month)
    period_end = _next_month(period_start)
    opening = _reconciliation_opening(lender_company_id, borrower_company_id, period_start)
    moves = _reconciliation_movements(lender_company_id, borrower_company_id, period_start, period_end)
    closing_liters = opening['liters'] + moves['issued_liters'] - moves['returned_liters']
    closing_kg = opening['kg'] + moves['issued_kg'] - moves['returned_kg']

    execute_query(
        """
        INSERT INTO company_reconciliation_acts (
            lender_company_id, borrower_company_id, period_month,
            act_number, act_date,
            opening_liters, opening_kg,
            issued_liters, issued_kg,
            returned_liters, returned_kg,
            closing_liters, closing_kg,
            note, created_by
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (lender_company_id, borrower_company_id, period_month)
        DO UPDATE SET
            act_number = EXCLUDED.act_number,
            act_date = EXCLUDED.act_date,
            opening_liters = EXCLUDED.opening_liters,
            opening_kg = EXCLUDED.opening_kg,
            issued_liters = EXCLUDED.issued_liters,
            issued_kg = EXCLUDED.issued_kg,
            returned_liters = EXCLUDED.returned_liters,
            returned_kg = EXCLUDED.returned_kg,
            closing_liters = EXCLUDED.closing_liters,
            closing_kg = EXCLUDED.closing_kg,
            note = EXCLUDED.note,
            created_by = EXCLUDED.created_by,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            lender_company_id,
            borrower_company_id,
            period_start,
            act_number,
            act_date,
            str(opening['liters']),
            str(opening['kg']),
            str(moves['issued_liters']),
            str(moves['issued_kg']),
            str(moves['returned_liters']),
            str(moves['returned_kg']),
            str(closing_liters),
            str(closing_kg),
            note,
            user['id'],
        ),
    )
    flash('Акт сверки за месяц сохранен.', 'success')
    return _recon_redirect(lender_company_id, borrower_company_id, period_month)