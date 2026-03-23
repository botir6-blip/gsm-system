from flask import Flask
from db import init_db

# routes
from routes.transactions import transactions_bp

app = Flask(__name__)
app.secret_key = "supersecretkey"

# DB
init_db()

# BLUEPRINTS
app.register_blueprint(transactions_bp)

if __name__ == "__main__":
    app.run(debug=True)
