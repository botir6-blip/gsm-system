from flask import Flask
from db import init_db
from routes.transactions import transactions_bp

app = Flask(__name__)
app.secret_key = "supersecretkey"

init_db()

app.register_blueprint(transactions_bp)

if __name__ == "__main__":
    app.run(debug=True)
