import os
from flask import Flask

from db import init_db
from routes.auth_routes import auth_bp
from routes.dashboard_routes import dashboard_bp
from routes.users_routes import users_bp
from routes.companies_routes import companies_bp
from routes.objects_routes import objects_bp
from routes.vehicles_routes import vehicles_bp
from routes.requests_routes import requests_bp
from routes.transactions_routes import transactions_bp

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "supersecretkey")

init_db()

app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(users_bp)
app.register_blueprint(companies_bp)
app.register_blueprint(objects_bp)
app.register_blueprint(vehicles_bp)
app.register_blueprint(requests_bp)
app.register_blueprint(transactions_bp)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
