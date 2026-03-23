import os
from flask import Flask
from db import init_db
from routes.transactions import transactions_bp

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "supersecretkey")

init_db()
app.register_blueprint(transactions_bp)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
