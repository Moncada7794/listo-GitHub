"""Aplicación web Cotuza Tours.

Este módulo implementa el backend de la aplicación web Cotuza Tours
utilizando Flask como framework web.

Attributes:
    app (Flask): Instancia principal de la aplicación Flask.
"""

import json, datetime, os
from dotenv import  load_dotenv
from flask import Flask, render_template, request, jsonify
import requests, uuid
from flask_sqlalchemy import  SQLAlchemy


load_dotenv()

# Inicialización de la aplicación Flask
app = Flask(__name__)


#connecion a base de dato

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

#Crear modelo de reservas

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tour_id = db.Column(db.Integer, nullable=False)
    date = db.Column(db.String(50), nullable=False)
    people = db.Column(db.Integer, nullable=False)
    email = db.Column(db.String(120), nullable=False)

#coneccion API para wompi



WOMPI_PUBLIC_KEY = os.getenv("WOMPI_PUBLIC_KEY")
WOMPI_PRIVATE_KEY = os.getenv("WOMPI_PRIVATE_KEY")
WOMPI_INTEGRITY_SECRET = os.getenv("WOMPI_INTEGRITY_SECRET")
WOMPI_API = os.getenv("WOMPI_API")


def load_tours():
    """Carga los datos de tours desde el archivo JSON.

    Lee el archivo tours.json ubicado en el directorio data/
    y retorna su contenido deserializado.

    Returns:
        list: Lista de diccionarios con la información de los tours.

    Raises:
        FileNotFoundError: Si el archivo tours.json no existe.
        json.JSONDecodeError: Si el archivo no contiene JSON válido.
    """
    with open("data/tours.json", "r", encoding="utf-8") as f:
        return json.load(f)


def load_bookings():
    with open("data/bookings.json", "r", encoding="utf-8") as f:
        return json.load(f)


def save_bookings(bookings):
    with open("data/bookings.json", "w", encoding="utf-8") as f:
        json.dump(bookings, f, indent=2)
        


@app.route("/")
def home():
    """Renderiza la página de inicio.

    Returns:
        str: HTML renderizado de la página index.html.
    """
    return render_template("index.html")


@app.route("/tours")
def tours():
    """Renderiza la página con el listado de todos los tours.

    Carga los datos de tours disponibles y los pasa al template
    para su visualización.

    Returns:
        str: HTML renderizado de la página tours.html con los datos de tours.
    """
    tours_data = load_tours()
    return render_template("tours.html", tours=tours_data)


@app.route("/tours/<int:tour_id>")
def tour_detail(tour_id):
    """Renderiza la página de detalle de un tour específico.

    Args:
        tour_id (int): Identificador único del tour.

    Returns:
        str: HTML renderizado de la página tour_detail.html si el tour existe.
        tuple: Mensaje de error y código HTTP 404 si el tour no se encuentra.
    """
    tours_data = load_tours()

    # Buscar tour por ID
    tour = next((t for t in tours_data if t["id"] == tour_id), None)

    if tour is None:
        return "Tour not found", 404

    return render_template("tour_detail.html", tour=tour)


@app.route("/calendar")
def calendar():
    """Renderiza la página del calendario.

    Returns:
        str: HTML renderizado de la página calendar.html.
    """
    return render_template("calendar.html")

@app.route("/api/book", methods=['POST'])
def book():
    data = request.json

    bookings = load_bookings()

    new_booking = {
        "tour_id": data["tour_id"],
        "date": data["date"],
        "name": data["name"],
        "email": data["email"]
    }
    bookings.append(new_booking)
    save_bookings(bookings)

    return jsonify({"status":"ok"})

@app.route("/api/bookings/<int:tour_id>")
def get_bookings(tour_id):
    bookings = Booking.query.filter_by(tour_id=tour_id).all()

    return jsonify([
        {
            "date": b.date
        }
        for b in bookings
    ])


@app.route("/gallery")
def gallery():
    """Renderiza la página de la galería.

    Returns:
        str: HTML renderizado de la página gallery.html.
    """
    return render_template("gallery.html")



@app.route("/create-payment", methods=["POST"])
def create_payment():
    data = request.json
    amount = int(data["amount"])

    try:
        #  Obtener token OAuth
        auth_response = requests.post(
            os.getenv("WOMPI_AUTH"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "client_credentials",
                "client_id": os.getenv("WOMPI_CLIENT_ID"),
                "client_secret": os.getenv("WOMPI_CLIENT_SECRET"),
                "audience": "wompi_api"
            }
        )

        token_data = auth_response.json()
        access_token = token_data.get("access_token")

        if not access_token:
            return jsonify({"error": "No access_token", "details": token_data}), 400

        #  Crear enlace de pago CORRECTO
        payment_response = requests.post(
            f"{os.getenv('WOMPI_API')}/EnlacePago",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            },
            json={
                "nombreProducto": "Reserva Cotuzas Tours",
                "descripcionProducto": f"Tour {data['tour_id']} - {data['people']} personas",
                "identificadorEnlaceComercio": f"tour-{data['tour_id']}-{data['date']}",
                "monto": amount,
                "moneda": "USD",
                "cantidadDisponible": 1,
                "vigencia": {
                    "tipo": "MINUTOS",
                    "valor": 1440
                },
                "urlRedirect": "http://localhost:5000/payment-success"
            }
        )

        payment_data = payment_response.json()

        print("WOMPI RESPONSE:", payment_data)

        url_pago = payment_data.get("urlEnlace")

        if not url_pago:
            return jsonify({
                "error": "No se generó enlace",
                "details": payment_data
            }), 400

        return jsonify({"checkout_url": url_pago})

    except Exception as e:
        return jsonify({"error": "Exception", "details": str(e)}), 500



@app.route("/payment-success")
def payment_success():
    transaction_id = request.args.get("id")

    if not transaction_id:
        return render_template("payment_success.html")

    headers = {
        "Authorization": f"Bearer {WOMPI_PRIVATE_KEY}"
    }

    # Consultar transacción en Wompi
    r = requests.get(f"{WOMPI_API}/transactions/{transaction_id}", headers=headers)
    data = r.json()

    # Verificar que el pago fue aprobado
    if data.get("data", {}).get("status") == "APPROVED":

        # Aquí recuperamos lo que guardaste en reference
        reference_data = data["data"]["reference"]

        pending = json.loads(reference_data)

        booking = Booking(
            tour_id=pending["tour_id"],
            date=pending["date"],
            people=pending["people"],
            email=pending["email"]
        )

        db.session.add(booking)
        db.session.commit()

    return render_template("payment_success.html")
@app.route("/wompi-webhook", methods=["POST"])

def wompi_webhook():
    data = request.json

    if data.get("estado") == "APROBADO":
        pass
        # guardar reserva en SQLite


# Punto de entrada de la aplicación
if __name__ == "__main__":
    app.run(debug=True)
