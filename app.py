from flask import Flask, request

app = Flask(__name__)

transactions = []

@app.route("/", methods=["GET", "POST"])
def home():

    if request.method == "POST":

        vehicle = request.form["vehicle"]
        obj = request.form["object"]
        liters = request.form["liters"]

        transactions.append({
            "vehicle": vehicle,
            "object": obj,
            "liters": liters
        })

    html = """
    <h2>GSM Заправка</h2>

    <form method="post">
    Машина: <input name="vehicle"><br><br>
    Объект: <input name="object"><br><br>
    Литр: <input name="liters"><br><br>
    <button>Сақлаш</button>
    </form>

    <h3>Журнал</h3>
    """

    for t in transactions:
        html += f"{t['vehicle']} - {t['object']} - {t['liters']}L <br>"

    return html


if __name__ == "__main__":
    app.run()
