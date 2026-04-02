from datetime import datetime, time
from decimal import Decimal, InvalidOperation

from flask import Blueprint, request, redirect, url_for, flash, jsonify
from db import (
    DEFAULT_DENSITY,
    POINT_TYPE_LABELS,
    WAREHOUSE_POINT_TYPES,
    fetch_all,
    fetch_one,
    execute_query,
)
from auth import login_required, role_required, get_current_user, get_scope_ids
from layout import render_page

fuel_bp = Blueprint("fuel_bp", __name__)

OPERATION_LABELS = {
    "INCOME": "Приход",
    "EXPENSE": "Расход",
    "TRANSFER_IN": "Перемещение в пункт",
    "TRANSFER_OUT": "Перемещение из пункта",
    "CORRECTION": "Корректировка",
}

STATUS_LABELS = {
    "approved": "Проверено",
    "pending": "Ожидает проверки",
    "rejected": "Отклонено",
}

INCOMING_TYPES = ("INCOME", "TRANSFER_IN", "CORRECTION")
OUTGOING_TYPES = ("EXPENSE", "TRANSFER_OUT")
DEFAULT_DENSITY_DECIMAL = Decimal(str(DEFAULT_DENSITY))
REFINERY_OPTIONS = ["ФНПЗ", "БНПЗ", "АНПЗ", "УНПЗ", "НПЗ Saneg"]
SOURCE_KIND_LABELS = {
    "refinery": "НПЗ / завод",
    "fuel_point": "Склад / АЗС / ПАЗС",
    "company": "Компания / контрагент",
    "other": "Другое",
}
DELIVERY_METHOD_LABELS = {
    "wagon": "Вагон",
    "truck": "Бензовоз",
    "transfer": "Внутреннее перемещение",
    "direct": "Прямой приход",
}
RECEIVER_POINT_TYPES = ("BRIGADE", "EXTERNAL_OBJECT", "AZS", "PAZS")


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


def _normalize_operation_date(raw_value):
    if raw_value:
        return datetime.fromisoformat(raw_value)
    return datetime.now()


def _decimal_to_string(value, places="0.0001"):
    if value is None:
        return None
    quant = Decimal(places)
    return str(value.quantize(quant))


def _point_is_warehouse(point):
    if not point:
        return False
    point_type = (point.get("point_type") or "").upper()
    name = (point.get("name") or "").lower()
    return point_type in WAREHOUSE_POINT_TYPES or "склад" in name or "гсм" in name


def _scope_ids(current_user):
    return get_scope_ids(current_user)


def _scoped_fuel_points(current_user):
    company_id, point_scope_id = _scope_ids(current_user)
    sql = "SELECT * FROM fuel_points WHERE is_active = TRUE"
    params = []
    if point_scope_id:
        sql += " AND id = %s"
        params.append(point_scope_id)
    elif current_user and current_user.get("role") != "admin" and company_id:
        sql += " AND company_id = %s"
        params.append(company_id)
    sql += " ORDER BY point_type, name"
    return fetch_all(sql, tuple(params))


def _scoped_companies(current_user):
    sql = "SELECT * FROM companies WHERE is_active = TRUE"
    params = []
    if current_user and current_user.get("role") != "admin" and current_user.get("company_id"):
        sql += " AND id = %s"
        params.append(current_user["company_id"])
    sql += " ORDER BY name"
    return fetch_all(sql, tuple(params))


def _scoped_point_by_id(point_id, current_user):
    company_id, point_scope_id = _scope_ids(current_user)
    sql = "SELECT * FROM fuel_points WHERE id = %s AND is_active = TRUE"
    params = [point_id]
    if point_scope_id:
        sql += " AND id = %s"
        params.append(point_scope_id)
    elif current_user and current_user.get("role") != "admin" and company_id:
        sql += " AND company_id = %s"
        params.append(company_id)
    return fetch_one(sql, tuple(params))


def _source_options(current_user):
    options = []
    for point in _scoped_fuel_points(current_user):
        options.append(point["name"])
    for company in _scoped_companies(current_user):
        options.append(company["name"])
    options.extend(REFINERY_OPTIONS)
    return sorted({item for item in options if item})


def _latest_opening_balance(fuel_point_id, op_dt):
    row = fetch_one(
        """
        SELECT balance_date, liters, kg, density, temperature
        FROM fuel_opening_balances
        WHERE fuel_point_id = %s
          AND balance_date <= %s
        ORDER BY balance_date DESC
        LIMIT 1
        """,
        (fuel_point_id, op_dt.date()),
    )
    if not row:
        return None

    liters = _to_decimal(row.get("liters")) or Decimal("0")
    density = _to_decimal(row.get("density"))
    kg = _to_decimal(row.get("kg"))
    if kg is None:
        kg = liters * (density or DEFAULT_DENSITY_DECIMAL)

    return {
        "balance_date": row["balance_date"],
        "liters": liters,
        "kg": kg,
        "density": density or (kg / liters if liters > 0 else DEFAULT_DENSITY_DECIMAL),
        "temperature": _to_decimal(row.get("temperature")),
    }


def _movement_delta_before(fuel_point_id, start_dt, op_dt):
    where_start = ""
    params = [
        tuple(INCOMING_TYPES),
        tuple(OUTGOING_TYPES),
        tuple(INCOMING_TYPES),
        DEFAULT_DENSITY,
        tuple(OUTGOING_TYPES),
        DEFAULT_DENSITY,
        fuel_point_id,
    ]
    if start_dt is not None:
        where_start = "AND operation_date >= %s"
        params.append(start_dt)
    params.append(op_dt)

    row = fetch_one(
        f"""
        SELECT
            COALESCE(SUM(
                CASE
                    WHEN operation_type IN %s AND status = 'approved' THEN liters
                    WHEN operation_type IN %s AND status <> 'rejected' THEN -liters
                    ELSE 0
                END
            ), 0) AS liters_delta,
            COALESCE(SUM(
                CASE
                    WHEN operation_type IN %s AND status = 'approved' THEN COALESCE(NULLIF(kg, 0), liters * COALESCE(density, %s))
                    WHEN operation_type IN %s AND status <> 'rejected' THEN -COALESCE(NULLIF(kg, 0), liters * COALESCE(density, %s))
                    ELSE 0
                END
            ), 0) AS kg_delta
        FROM fuel_transactions
        WHERE fuel_point_id = %s
          {where_start}
          AND operation_date < %s
        """,
        tuple(params),
    )

    return {
        "liters": _to_decimal(row.get("liters_delta")) or Decimal("0"),
        "kg": _to_decimal(row.get("kg_delta")) or Decimal("0"),
    }


def get_point_state_before(fuel_point_id, op_dt):
    opening = _latest_opening_balance(fuel_point_id, op_dt)
    if opening:
        start_dt = datetime.combine(opening["balance_date"], time.min)
        liters = opening["liters"]
        kg = opening["kg"]
    else:
        start_dt = None
        liters = Decimal("0")
        kg = Decimal("0")

    movement = _movement_delta_before(fuel_point_id, start_dt, op_dt)
    liters += movement["liters"]
    kg += movement["kg"]
    avg_density = (kg / liters) if liters > 0 else DEFAULT_DENSITY_DECIMAL

    return {"current_liters": liters, "current_kg": kg, "avg_density": avg_density}


def _resolve_mass_values(liters, kg, density, fallback_density):
    density = density or fallback_density or DEFAULT_DENSITY_DECIMAL

    if liters is None and kg is None:
        return None, None, density

    if liters is None and kg is not None:
        liters = kg / density if density else None
    elif kg is None and liters is not None:
        kg = liters * density if density else None
    elif density is None and liters and kg:
        density = kg / liters

    return liters, kg, density


@fuel_bp.route("/fuel/journal")
@login_required
@role_required("admin", "fuel_operator", "ats", "viewer")
def fuel_journal():
    current_user = get_current_user()
    company_id, point_scope_id = _scope_ids(current_user)

    point_id = request.args.get("point_id") or ""
    operation_type = request.args.get("operation_type") or ""
    status = request.args.get("status") or ""
    receiver_type = request.args.get("receiver_type") or ""
    date_from = request.args.get("date_from") or ""
    date_to = request.args.get("date_to") or ""
    q = (request.args.get("q") or "").strip()

    journal_sql = """
        SELECT
            ft.*,
            fp.name AS fuel_point_name,
            fp.point_type,
            sc.name AS source_company_name,
            v.plate_number,
            v.brand,
            v.division_name,
            rc.name AS responsible_company_name,
            dp.name AS destination_point_name,
            u.full_name AS entered_by_name,
            au.full_name AS ats_name
        FROM fuel_transactions ft
        LEFT JOIN fuel_points fp ON fp.id = ft.fuel_point_id
        LEFT JOIN fuel_points dp ON dp.id = ft.destination_point_id
        LEFT JOIN companies sc ON sc.id = fp.company_id
        LEFT JOIN vehicles v ON v.id = ft.vehicle_id
        LEFT JOIN companies rc ON rc.id = ft.responsible_company_id
        LEFT JOIN users u ON u.id = ft.entered_by
        LEFT JOIN users au ON au.id = ft.ats_checked_by
        WHERE 1=1
    """
    params = []

    if point_scope_id:
        journal_sql += " AND ft.fuel_point_id = %s"
        params.append(point_scope_id)
    elif current_user and current_user.get("role") != "admin" and company_id:
        journal_sql += " AND fp.company_id = %s"
        params.append(company_id)

    if point_id:
        journal_sql += " AND ft.fuel_point_id = %s"
        params.append(point_id)
    if operation_type:
        journal_sql += " AND ft.operation_type = %s"
        params.append(operation_type)
    if status:
        journal_sql += " AND ft.status = %s"
        params.append(status)
    if receiver_type:
        journal_sql += " AND ft.receiver_type = %s"
        params.append(receiver_type)
    if date_from:
        journal_sql += " AND ft.operation_date >= %s"
        params.append(f"{date_from} 00:00:00")
    if date_to:
        journal_sql += " AND ft.operation_date <= %s"
        params.append(f"{date_to} 23:59:59")
    if q:
        like = f"%{q}%"
        journal_sql += """
            AND (
                COALESCE(fp.name, '') ILIKE %s OR
                COALESCE(v.plate_number, '') ILIKE %s OR
                COALESCE(v.brand, '') ILIKE %s OR
                COALESCE(v.division_name, '') ILIKE %s OR
                COALESCE(ft.destination_name, '') ILIKE %s OR
                COALESCE(dp.name, '') ILIKE %s OR
                COALESCE(ft.source_info, '') ILIKE %s OR
                COALESCE(ft.document_number, '') ILIKE %s OR
                COALESCE(ft.comment, '') ILIKE %s OR
                COALESCE(ft.driver_name, '') ILIKE %s
            )
        """
        params.extend([like] * 10)

    try:
        page = max(int(request.args.get("page", 1)), 1)
    except (TypeError, ValueError):
        page = 1
    page_size = 50
    offset = (page - 1) * page_size

    journal_sql += " ORDER BY ft.operation_date DESC, ft.id DESC LIMIT %s OFFSET %s"
    params.extend([page_size + 1, offset])
    rows = fetch_all(journal_sql, tuple(params))
    has_next = len(rows) > page_size
    rows = rows[:page_size]

    return render_page(
        "fuel_journal.html",
        rows=rows,
        operation_labels=OPERATION_LABELS,
        status_labels=STATUS_LABELS,
        point_type_labels=POINT_TYPE_LABELS,
        filters={
            "point_id": point_id,
            "operation_type": operation_type,
            "status": status,
            "receiver_type": receiver_type,
            "date_from": date_from,
            "date_to": date_to,
            "q": q,
        },
        filter_points=_scoped_fuel_points(current_user),
        pagination={"page": page, "has_prev": page > 1, "has_next": has_next},
        source_kind_labels=SOURCE_KIND_LABELS,
        delivery_method_labels=DELIVERY_METHOD_LABELS,
    )


@fuel_bp.route("/fuel/income", methods=["GET", "POST"])
@login_required
@role_required("admin", "fuel_operator")
def fuel_income():
    current_user = get_current_user()

    if request.method == "POST":
        fuel_point_id = request.form.get("fuel_point_id")
        point = _scoped_point_by_id(fuel_point_id, current_user)
        if not point:
            flash("Пункт топлива не найден или недоступен.", "danger")
            return redirect(url_for("fuel_bp.fuel_income"))

        operation_date = request.form.get("operation_date")
        document_date = request.form.get("document_date") or None
        liters = _to_decimal(request.form.get("liters"))
        kg = _to_decimal(request.form.get("kg"))
        density = _to_decimal(request.form.get("density"))
        temperature = _to_decimal(request.form.get("temperature"))
        source_kind = (request.form.get("source_kind") or "").strip() or None
        source_info = (request.form.get("source_info") or "").strip()
        delivery_method = (request.form.get("delivery_method") or "").strip() or None
        transport_reference = (request.form.get("transport_reference") or "").strip() or None
        document_number = request.form.get("document_number", "").strip()
        comment = request.form.get("comment", "").strip()

        liters, kg, density = _resolve_mass_values(liters, kg, density, DEFAULT_DENSITY_DECIMAL)
        if liters is None:
            flash("Для прихода нужно указать литры или кг вместе с уд. весом.", "warning")
            return redirect(url_for("fuel_bp.fuel_income"))

        if not source_info:
            flash("Укажите источник поступления.", "warning")
            return redirect(url_for("fuel_bp.fuel_income"))

        execute_query(
            """
            INSERT INTO fuel_transactions
            (
                operation_date, document_date, fuel_point_id, operation_type, liters, kg, density, temperature,
                source_kind, source_info, delivery_method, transport_reference,
                document_number, comment, entered_by
            )
            VALUES (%s, %s, %s, 'INCOME', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                operation_date,
                document_date,
                fuel_point_id,
                _decimal_to_string(liters, "0.01"),
                _decimal_to_string(kg, "0.01"),
                _decimal_to_string(density, "0.0001"),
                _decimal_to_string(temperature, "0.01") if temperature is not None else None,
                source_kind,
                source_info,
                delivery_method,
                transport_reference,
                document_number,
                comment,
                current_user["id"],
            ),
        )

        flash("Приход сохранен и отправлен на проверку АТС.", "success")
        return redirect(url_for("fuel_bp.fuel_journal"))

    return render_page(
        "fuel_income.html",
        fuel_points=_scoped_fuel_points(current_user),
        point_type_labels=POINT_TYPE_LABELS,
        source_options=_source_options(current_user),
        source_kind_labels=SOURCE_KIND_LABELS,
        delivery_method_labels=DELIVERY_METHOD_LABELS,
    )


@fuel_bp.route("/fuel/expense", methods=["GET", "POST"])
@login_required
@role_required("admin", "fuel_operator")
def fuel_expense():
    current_user = get_current_user()

    if request.method == "POST":
        fuel_point_id = request.form.get("fuel_point_id")
        point = _scoped_point_by_id(fuel_point_id, current_user)
        if not point:
            flash("Пункт топлива не найден или недоступен.", "danger")
            return redirect(url_for("fuel_bp.fuel_expense"))

        operation_date_raw = request.form.get("operation_date")
        operation_dt = _normalize_operation_date(operation_date_raw)
        receiver_type = request.form.get("receiver_type", "vehicle")
        vehicle_id = request.form.get("vehicle_id") or None
        destination_point_id = request.form.get("destination_point_id") or None
        destination_name = (request.form.get("destination_name") or "").strip() or None
        liters = _to_decimal(request.form.get("liters"))
        kg = _to_decimal(request.form.get("kg"))
        density = _to_decimal(request.form.get("density"))
        temperature = _to_decimal(request.form.get("temperature"))
        speedometer = None
        moto_hours = None
        waybill_number = request.form.get("waybill_number", "").strip()
        driver_name = request.form.get("driver_name", "").strip()
        task_basis = request.form.get("task_basis", "").strip()
        work_purpose = request.form.get("work_purpose", "").strip()
        responsible_company_id = None
        comment = request.form.get("comment", "").strip()

        point_state = get_point_state_before(int(fuel_point_id), operation_dt)
        auto_density = point_state["avg_density"]
        is_warehouse = _point_is_warehouse(point)

        if is_warehouse:
            liters, kg, density = _resolve_mass_values(liters, kg, density, auto_density)
            if liters is None or kg is None:
                flash("Для склада нужно указать литры или кг. Недостающее значение программа рассчитает по уд. весу.", "warning")
                return redirect(url_for("fuel_bp.fuel_expense"))
        else:
            if liters is None:
                flash("Для расхода с АЗС, ПАЗС или объекта укажите литры.", "warning")
                return redirect(url_for("fuel_bp.fuel_expense"))
            liters, kg, density = _resolve_mass_values(liters, None, density, auto_density)

        if receiver_type == "vehicle":
            if not vehicle_id:
                flash("Выберите транспорт.", "warning")
                return redirect(url_for("fuel_bp.fuel_expense"))
            destination_point_id = None
        else:
            vehicle_id = None
            waybill_number = ""
            if destination_point_id:
                dest_point = _scoped_point_by_id(destination_point_id, current_user)
                if dest_point:
                    destination_name = dest_point["name"]
                else:
                    destination_point_id = None
            if not destination_name:
                flash("Укажите получателя для расхода не на транспорт.", "warning")
                return redirect(url_for("fuel_bp.fuel_expense"))

        execute_query(
            """
            INSERT INTO fuel_transactions
            (
                operation_date, fuel_point_id, operation_type, receiver_type,
                liters, kg, density, temperature, vehicle_id, destination_name, destination_point_id,
                speedometer, moto_hours, waybill_number, driver_name, task_basis, work_purpose,
                responsible_company_id, comment, entered_by
            )
            VALUES (%s, %s, 'EXPENSE', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                operation_date_raw,
                fuel_point_id,
                receiver_type,
                _decimal_to_string(liters, "0.01"),
                _decimal_to_string(kg, "0.01"),
                _decimal_to_string(density, "0.0001"),
                _decimal_to_string(temperature, "0.01") if temperature is not None else None,
                vehicle_id,
                destination_name,
                destination_point_id,
                speedometer,
                moto_hours,
                waybill_number,
                driver_name,
                task_basis,
                work_purpose,
                responsible_company_id,
                comment,
                current_user["id"],
            ),
        )

        flash("Расход сохранен и отправлен на проверку АТС.", "success")
        return redirect(url_for("fuel_bp.fuel_journal"))

    return render_page(
        "fuel_expense.html",
        fuel_points=_scoped_fuel_points(current_user),
        point_type_labels=POINT_TYPE_LABELS,
    )


@fuel_bp.route("/fuel/opening-balances", methods=["GET", "POST"])
@login_required
@role_required("admin")
def opening_balances():
    current_user = get_current_user()
    if request.method == "POST":
        fuel_point_id = request.form.get("fuel_point_id")
        balance_date = request.form.get("balance_date")
        liters = _to_decimal(request.form.get("liters"))
        kg = _to_decimal(request.form.get("kg"))
        density = _to_decimal(request.form.get("density"))
        temperature = _to_decimal(request.form.get("temperature"))
        comment = (request.form.get("comment") or "").strip()

        liters, kg, density = _resolve_mass_values(liters, kg, density, DEFAULT_DENSITY_DECIMAL)
        if not fuel_point_id or not balance_date or liters is None:
            flash("Укажите дату, пункт топлива и минимум литры либо кг с уд. весом.", "warning")
            return redirect(url_for("fuel_bp.opening_balances"))

        execute_query(
            """
            INSERT INTO fuel_opening_balances
            (fuel_point_id, balance_date, liters, kg, density, temperature, comment, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (fuel_point_id, balance_date)
            DO UPDATE SET
                liters = EXCLUDED.liters,
                kg = EXCLUDED.kg,
                density = EXCLUDED.density,
                temperature = EXCLUDED.temperature,
                comment = EXCLUDED.comment,
                created_by = EXCLUDED.created_by
            """,
            (
                fuel_point_id,
                balance_date,
                _decimal_to_string(liters, "0.01"),
                _decimal_to_string(kg, "0.01"),
                _decimal_to_string(density, "0.0001"),
                _decimal_to_string(temperature, "0.01") if temperature is not None else None,
                comment,
                current_user["id"],
            ),
        )
        flash("Начальный остаток сохранён.", "success")
        return redirect(url_for("fuel_bp.opening_balances"))

    rows_sql = """
        SELECT ob.*, fp.name AS fuel_point_name, fp.point_type, u.full_name AS created_by_name
        FROM fuel_opening_balances ob
        LEFT JOIN fuel_points fp ON fp.id = ob.fuel_point_id
        LEFT JOIN users u ON u.id = ob.created_by
        WHERE 1=1
    """
    params = []
    company_id, point_scope_id = _scope_ids(current_user)
    if point_scope_id:
        rows_sql += " AND ob.fuel_point_id = %s"
        params.append(point_scope_id)
    elif current_user and current_user.get("role") != "admin" and company_id:
        rows_sql += " AND fp.company_id = %s"
        params.append(company_id)
    rows_sql += " ORDER BY ob.balance_date DESC, fp.name"

    return render_page(
        "opening_balances.html",
        fuel_points=_scoped_fuel_points(current_user),
        rows=fetch_all(rows_sql, tuple(params)),
        point_type_labels=POINT_TYPE_LABELS,
    )


@fuel_bp.route("/fuel/opening-balances/delete/<int:item_id>", methods=["POST"])
@login_required
@role_required("admin")
def delete_opening_balance(item_id):
    execute_query("DELETE FROM fuel_opening_balances WHERE id = %s", (item_id,))
    flash("Начальный остаток удалён.", "info")
    return redirect(url_for("fuel_bp.opening_balances"))


@fuel_bp.route("/fuel/vehicles/search")
@login_required
def search_vehicles():
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify([])

    current_user = get_current_user()
    sql = """
        SELECT
            v.id,
            v.brand,
            v.plate_number,
            v.vehicle_type,
            v.division_name,
            c.name AS company_name,
            v.fuel_rate_km,
            v.fuel_rate_mh,
            v.fuel_rate_ground,
            v.fuel_rate_climate,
            v.fuel_rate_special,
            v.fuel_rate_stops,
            v.fuel_rate_load_30,
            v.fuel_rate_load_60,
            v.fuel_rate_load_75
        FROM vehicles v
        LEFT JOIN companies c ON c.id = v.company_id
        WHERE v.is_active = TRUE
          AND (
              v.plate_number ILIKE %s OR
              v.brand ILIKE %s OR
              v.vehicle_type ILIKE %s OR
              COALESCE(v.division_name, '') ILIKE %s
          )
    """
    params = [f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%"]
    if current_user and current_user.get("role") != "admin" and current_user.get("company_id"):
        sql += " AND v.company_id = %s"
        params.append(current_user["company_id"])
    sql += " ORDER BY v.plate_number LIMIT 20"
    return jsonify(fetch_all(sql, tuple(params)))


@fuel_bp.route("/fuel/receivers/search")
@login_required
def search_receivers():
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify([])

    current_user = get_current_user()
    sql = """
        SELECT id, name, point_type, address
        FROM fuel_points
        WHERE is_active = TRUE
          AND point_type IN %s
          AND (name ILIKE %s OR COALESCE(address, '') ILIKE %s)
    """
    params = [tuple(RECEIVER_POINT_TYPES), f"%{q}%", f"%{q}%"]
    company_id, point_scope_id = _scope_ids(current_user)
    if point_scope_id:
        sql += " AND id = %s"
        params.append(point_scope_id)
    elif current_user and current_user.get("role") != "admin" and company_id:
        sql += " AND company_id = %s"
        params.append(company_id)
    sql += " ORDER BY point_type, name LIMIT 20"
    rows = fetch_all(sql, tuple(params))
    for row in rows:
        row["point_type_label"] = POINT_TYPE_LABELS.get(row["point_type"], row["point_type"])
    return jsonify(rows)


@fuel_bp.route("/fuel/point-metrics/<int:point_id>")
@login_required
def point_metrics(point_id):
    point = _scoped_point_by_id(point_id, get_current_user())
    if not point:
        return jsonify({"error": "not_found"}), 404

    operation_date = _normalize_operation_date(request.args.get("operation_date"))
    state = get_point_state_before(point_id, operation_date)
    return jsonify(
        {
            "point_id": point_id,
            "point_name": point.get("name"),
            "point_type": point.get("point_type"),
            "point_type_label": POINT_TYPE_LABELS.get(point.get("point_type"), point.get("point_type")),
            "is_warehouse": _point_is_warehouse(point),
            "current_liters": float(state["current_liters"]),
            "current_kg": float(state["current_kg"]),
            "avg_density": float(state["avg_density"]),
            "kg_is_estimated": not _point_is_warehouse(point),
        }
    )
