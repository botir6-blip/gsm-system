from flask import render_template_string
from auth import current_user

BASE_HTML = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>{{ title }}</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background: linear-gradient(135deg, #eef4ff 0%, #f7fbff 100%);
            margin: 0;
            padding: 20px;
            color: #1f2937;
        }
        .container {
            max-width: 1360px;
            margin: auto;
            background: #ffffff;
            padding: 22px;
            border-radius: 18px;
            box-shadow: 0 10px 30px rgba(31,41,55,0.08);
        }
        .site-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 16px;
            padding: 14px 18px;
            margin-bottom: 18px;
            border-radius: 16px;
            background: linear-gradient(90deg, #0f172a 0%, #1d4ed8 100%);
            color: #ffffff;
            box-shadow: 0 10px 25px rgba(29,78,216,0.18);
            flex-wrap: wrap;
        }
        .brand {
            display: flex;
            align-items: center;
            gap: 14px;
            min-width: 0;
        }
        .brand-logo-wrap {
            background: #ffffff;
            padding: 6px 10px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .brand-logo {
            height: 46px;
            width: auto;
            display: block;
        }
        .brand-text {
            min-width: 0;
        }
        .brand-title {
            font-size: 22px;
            font-weight: 700;
            line-height: 1.1;
            margin: 0;
        }
        .brand-subtitle {
            font-size: 13px;
            opacity: 0.9;
            margin-top: 4px;
        }
        .topbar {
            display: flex;
            justify-content: space-between;
            gap: 12px;
            align-items: center;
            margin-bottom: 18px;
            flex-wrap: wrap;
        }
        .page-title {
            margin: 0;
            font-size: 28px;
        }
        .userbox {
            background: #ffffff;
            border: 1px solid #dbe4f0;
            padding: 10px 14px;
            border-radius: 12px;
            font-size: 14px;
            color: #111827;   /* 🔥 ЭНГ МУҲИМ */
            box-shadow: 0 4px 12px rgba(0,0,0,0.08);
        }
        h1, h2, h3 { margin-top: 0; }
        .menu {
            margin-bottom: 20px;
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
        }
        .menu a {
            text-decoration: none;
            background: #2563eb;
            color: white;
            padding: 10px 14px;
            border-radius: 10px;
            display: inline-block;
            font-size: 14px;
            box-shadow: 0 4px 12px rgba(37,99,235,0.18);
        }
        .menu a:hover { background: #1d4ed8; }
        .dashboard {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 16px;
            margin-bottom: 18px;
        }
        .stat {
            background: linear-gradient(135deg, #ffffff 0%, #f7faff 100%);
            border: 1px solid #dbe4f0;
            border-radius: 16px;
            padding: 18px;
            box-shadow: 0 6px 18px rgba(31,41,55,0.06);
        }
        .stat .label {
            font-size: 13px;
            color: #6b7280;
            margin-bottom: 8px;
        }
        .stat .value {
            font-size: 28px;
            font-weight: bold;
        }
        .grid-2 {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 18px;
        }
        .card {
            background: #f9fbff;
            border: 1px solid #e3ebf5;
            padding: 18px;
            border-radius: 16px;
            margin-bottom: 18px;
            box-shadow: 0 6px 16px rgba(31,41,55,0.05);
        }
        form { display: grid; gap: 12px; }
        input, select, textarea, button {
            padding: 12px;
            border-radius: 12px;
            border: 1px solid #cfd8e3;
            font-size: 15px;
            box-sizing: border-box;
            width: 100%;
            background: #fff;
        }
        textarea {
            min-height: 90px;
            resize: vertical;
        }
        button {
            background: linear-gradient(135deg, #16a34a 0%, #179c54 100%);
            color: white;
            border: none;
            cursor: pointer;
            font-weight: bold;
            box-shadow: 0 6px 16px rgba(22,163,74,0.2);
        }
        button:hover { background: #15803d; }
        .btn-red {
            background: linear-gradient(135deg, #dc2626 0%, #c81e1e 100%) !important;
        }
        .btn-red:hover { background: #b91c1c !important; }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
            background: white;
            font-size: 14px;
            border-radius: 14px;
            overflow: hidden;
        }
        th, td {
            border: 1px solid #e5e7eb;
            padding: 10px;
            text-align: left;
            vertical-align: top;
        }
        th { background: #eef4fb; }
        .flash {
            padding: 12px;
            border-radius: 12px;
            margin-bottom: 15px;
        }
        .success {
            background: #dcfce7;
            color: #166534;
        }
        .error {
            background: #fee2e2;
            color: #991b1b;
        }
        .actions {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
        }
        .btn {
            padding: 7px 10px;
            color: white;
            border-radius: 9px;
            text-decoration: none;
            font-size: 13px;
            display: inline-block;
        }
        .btn-edit { background: #f59e0b; }
        .btn-edit:hover { background: #d97706; }
        .btn-delete { background: #dc2626; }
        .btn-delete:hover { background: #b91c1c; }
        .btn-view { background: #2563eb; }
        .btn-view:hover { background: #1d4ed8; }
        .btn-approve { background: #0ea5e9; }
        .btn-approve:hover { background: #0284c7; }
        .btn-fuel { background: #16a34a; }
        .btn-fuel:hover { background: #15803d; }
        .btn-check { background: #7c3aed; }
        .btn-check:hover { background: #6d28d9; }
        .btn-back { background: #6b7280; }
        .btn-back:hover { background: #4b5563; }
        .status {
            display: inline-block;
            padding: 5px 10px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: bold;
            color: #fff;
        }
        .status-new { background: #6b7280; }
        .status-approved { background: #0ea5e9; }
        .status-fueled { background: #16a34a; }
        .status-checked { background: #7c3aed; }
        .status-rejected { background: #dc2626; }

        @media (max-width: 1100px) {
            .dashboard { grid-template-columns: repeat(2, 1fr); }
            .grid-2 { grid-template-columns: 1fr; }
        }
        @media (max-width: 700px) {
            body { padding: 12px; }
            .dashboard { grid-template-columns: 1fr; }
            .container { padding: 14px; }
            table { font-size: 13px; }
            .brand-logo { height: 38px; }
            .brand-title { font-size: 18px; }
            .page-title { font-size: 22px; }
        }
    </style>
</head>
<body>
<div class="container">

    <div class="site-header">
        <div class="brand">
            <div class="brand-logo-wrap">
                <img src="/static/logo.png" alt="ERIELL" class="brand-logo">
            </div>
            <div class="brand-text">
                <div class="brand-title">ERIELL</div>
                <div class="brand-subtitle">Система контроля ГСМ</div>
            </div>
        </div>
        {{ user_box|safe }}
    </div>

    <div class="topbar">
        <h1 class="page-title">{{ title }}</h1>
    </div>

    {{ menu|safe }}

    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        {% for category, message in messages %}
          <div class="flash {{ category }}">{{ message }}</div>
        {% endfor %}
      {% endif %}
    {% endwith %}

    {{ content|safe }}
</div>
</body>
</html>
"""


def nav_menu():
    user = current_user()
    if not user:
        return """
        <div class="menu">
            <a href="/login">Вход</a>
        </div>
        """

    menu = ['<a href="/">Главная</a>']

    if user["role"] == "admin":
        menu += [
            '<a href="/companies">Компании</a>',
            '<a href="/objects">Объекты</a>',
            '<a href="/vehicles">Транспорт</a>',
            '<a href="/users">Пользователи</a>',
        ]

    if user["role"] in ["admin", "requester"]:
        menu.append('<a href="/requests/new">Новая заявка</a>')

    if user["role"] in ["admin", "requester", "internal_approver", "external_approver", "fueler", "controller"]:
        menu.append('<a href="/requests">Заявки</a>')

    if user["role"] in ["admin", "requester", "internal_approver", "external_approver", "fueler", "controller", "ats_operator"]:
        menu.append('<a href="/transactions">Журнал</a>')

    menu.append('<a href="/logout">Выход</a>')

    return f'<div class="menu">{"".join(menu)}</div>'


def render_page(title, content):
    user = current_user()
    if user:
        user_box = f"""
        <div class="userbox">
            <b>{user['full_name']}</b><br>
            Логин: {user['username']} |
            Роль: {role_ru(user['role'])} |
            Компания: {user['company_name'] or '-'}
        </div>
        """
    else:
        user_box = '<div class="userbox">Гость</div>'

    return render_template_string(
        BASE_HTML,
        title=title,
        content=content,
        menu=nav_menu(),
        user_box=user_box
    )

def role_ru(role):
    mapping = {
        "admin": "Администратор",
        "requester": "Инициатор заявки",
        "internal_approver": "Согласующий (внутренний)",
        "external_approver": "Согласующий (внешний)",
        "fueler": "Оператор заправки",
        "controller": "Контролёр",
        "ats_operator": "АТС оператор",
    }
    return mapping.get(role, role)

def status_badge(status):
    labels = {
        "new": ("Новая", "status-new"),
        "approved": ("Разрешена", "status-approved"),
        "fueled": ("Заправлена", "status-fueled"),
        "checked": ("Проверена", "status-checked"),
        "rejected": ("Отклонена", "status-rejected"),
    }
    text, css = labels.get(status, (status, "status-new"))
    return f'<span class="status {css}">{text}</span>'
