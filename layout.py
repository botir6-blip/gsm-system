from flask import render_template_string, url_for
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
        .topbar {
            display: flex;
            justify-content: space-between;
            gap: 12px;
            align-items: center;
            margin-bottom: 18px;
            flex-wrap: wrap;
        }
        .userbox {
            background: #f3f6fb;
            border: 1px solid #dbe4f0;
            padding: 10px 14px;
            border-radius: 12px;
            font-size: 14px;
        }
        h1, h2, h3 {
            margin-top: 0;
        }
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
        .menu a:hover {
            background: #1d4ed8;
        }
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
        form {
            display: grid;
            gap: 12px;
        }
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
        button:hover {
            background: #15803d;
        }
        .btn-red {
            background: linear-gradient(135deg, #dc2626 0%, #c81e1e 100%) !important;
        }
        .btn-red:hover {
            background: #b91c1c !important;
        }
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
        th {
            background: #eef4fb;
        }
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
            .dashboard { grid-template-columns: 1fr; }
            .container { padding: 14px; }
            table { font-size: 13px; }
        }
    </style>
</head>
<body>
<div class="container">
    <div class="topbar">
        <h1>{{ title }}</h1>
        {{ user_box|safe }}
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
        return f"""
        <div class="menu">
            <a href="{url_for('login')}">Вход</a>
        </div>
        """

    menu = [f'<a href="{url_for("index")}">Главная</a>']

    if user["role"] == "admin":
        menu += [
            f'<a href="{url_for("companies_page")}">Компании</a>',
            f'<a href="{url_for("objects_page")}">Объекты</a>',
            f'<a href="{url_for("vehicles_page")}">Транспорт</a>',
            f'<a href="{url_for("users_page")}">Пользователи</a>',
        ]

    if user["role"] in ["admin", "requester"]:
        menu.append(f'<a href="{url_for("new_request_page")}">Новая заявка</a>')

    menu.append(f'<a href="{url_for("requests_page")}">Заявки</a>')
    menu.append(f'<a href="{url_for("transactions_page")}">Журнал</a>')
    menu.append(f'<a href="{url_for("logout")}">Выход</a>')

    return f'<div class="menu">{"".join(menu)}</div>'


def render_page(title, content):
    user = current_user()
    if user:
        user_box = f"""
        <div class="userbox">
            <b>{user['full_name']}</b><br>
            Логин: {user['username']} |
            Роль: {user['role']} |
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
