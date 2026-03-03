"""Aplicación web Cotuza Tours.

Este módulo implementa el backend de la aplicación web Cotuza Tours
utilizando Flask como framework web.

Attributes:
    app (Flask): Instancia principal de la aplicación Flask.
"""

import json, datetime, os
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, redirect
import requests, uuid
from flask_sqlalchemy import SQLAlchemy
import urllib.parse

load_dotenv()

# Inicialización de la aplicación Flask
app = Flask(__name__)

# connecion a base de dato

app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

database_url = os.getenv("DATABASE_URL")

if database_url:
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://")

app.config["SQLALCHEMY_DATABASE_URI"] = database_url

# PAra correr localhost y hacer pruebas

"""database_url = os.getenv("DATABASE_URL")

if database_url:
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://")
else:
    database_url = "sqlite:///database.db"  # ← LOCAL

app.config["SQLALCHEMY_DATABASE_URI"] = database_url"""


# Crear modelo de reservas

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tour_id = db.Column(db.Integer, nullable=False)
    date = db.Column(db.String(50), nullable=False)
    people = db.Column(db.Integer, nullable=False)
    email = db.Column(db.String(120), nullable=False)


# Crear base  de datos

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True)

# coneccion API para wompi


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

def send_whatsapp_notifications(message):
    numbers = [
        os.getenv("WHATSAPP_NUMBER_1"),
        os.getenv("WHATSAPP_NUMBER_2")
    ]

    for number in numbers:
        if number:
            try:
                requests.get(
                    url="https://api.whatsapp.com/send",
                    params={
                        "phone": number,
                        "text": message
                    },
                    timeout=5
                )
            except Exception as e:
                print("WhatsApp error:", e)

@app.route("/")
def home():
    """Renderiza la página de inicio.

    Returns:
        str: HTML renderizado de la página index.html.
    """
    tours_data = load_tours()
    return render_template("index.html", tours=tours_data)


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

    return jsonify({"status": "ok"})


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

    tours_data = load_tours()

    # =====================================================
    #  CASO 1 — PAGO DESDE CARRITO (MULTI-TOUR)
    # =====================================================
    cart_data = request.form.get("cart_data")

    if cart_data:
        try:
            cart = json.loads(cart_data)
        except Exception:
            return jsonify({"error": "Invalid cart data"}), 400

        if not cart:
            return jsonify({"error": "Empty cart"}), 400

        total = sum(item.get("price", 0) for item in cart)

        reference_payload = json.dumps({
            "cart": cart
        })

        product_name = "Cotuza Tours – Multi-Tour Booking"
        product_desc = f"{len(cart)} tours"

    # =====================================================
    #  CASO 2 — PAGO INDIVIDUAL ( FLUJO ACTUAL)
    # =====================================================
    else:
        tour_id = int(request.form.get("tour_id"))
        date = request.form.get("date")
        people = int(request.form.get("people"))
        email = request.form.get("email")
        pickup = request.form.get("pickup")

        tour = next((t for t in tours_data if t["id"] == tour_id), None)
        if not tour:
            return "Tour not found", 404

        price_one = tour["pricing"]["one"]
        price_group = tour["pricing"]["group"]

        total = price_one if people == 1 else price_group * people

        if pickup == "airport":
            total += 49.99

        reference_payload = json.dumps({
            "tour_id": tour_id,
            "date": date,
            "people": people,
            "email": email
        })

        product_name = tour["name"]
        product_desc = f"{people} personas – {date}"

    # =====================================================
    # 🔐 TOKEN WOMPI (NO TOCAR)
    # =====================================================
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

    # =====================================================
    #  CREAR LINK WOMPI
    # =====================================================
    payment_response = requests.post(
        f"{os.getenv('WOMPI_API')}/EnlacePago",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        },
        json={
            "nombreProducto": product_name,
            "descripcionProducto": product_desc,
            "identificadorEnlaceComercio": f"tour-{uuid.uuid4()}",
            "monto": round(total, 2),
            "moneda": "USD",
            "cantidadDisponible": 1,
            "referencia": reference_payload,
            "vigencia": {"tipo": "MINUTOS", "valor": 1440},
            "urlRedirect": "https://hikingelsalvador.com/payment-success"
        }
    )

    payment_data = payment_response.json()
    url_pago = payment_data.get("urlEnlace")

    if not url_pago:
        return jsonify({"error": "No payment link", "details": payment_data}), 400

    return redirect(url_pago)


@app.route("/payment-success")
def payment_success():
    transaction_id = request.args.get("id")

    if not transaction_id:
        return render_template("payment_success.html")

    headers = {
        "Authorization": f"Bearer {WOMPI_PRIVATE_KEY}"
    }

    r = requests.get(f"{WOMPI_API}/transactions/{transaction_id}", headers=headers)
    data = r.json()

    if data.get("data", {}).get("status") == "APPROVED":

        reference_data = data["data"].get("reference")

        if reference_data:
            pending = json.loads(reference_data)

            tours_data = load_tours()

            # =================================================
            #  CASO 1 — CARRITO (multi tours)
            # =================================================
            if "cart" in pending:

                for item in pending["cart"]:
                    booking = Booking(
                        tour_id=item["tour_id"],
                        date=item["date"],
                        people=item["people"],
                        email=pending["email"]
                    )
                    db.session.add(booking)

                db.session.commit()

                # ==============================
                #  WhatsApp automático (carrito)
                # ==============================
                msg_lines = [
                    "✅ NEW PAID BOOKING",
                    ""
                ]

                for item in pending["cart"]:
                    tour_name = next(
                        (t["name"] for t in tours_data if t["id"] == item["tour_id"]),
                        "Tour"
                    )

                    msg_lines.append(f"• {tour_name}")
                    msg_lines.append(f"  📅 {item['date']}")
                    msg_lines.append(f"  👥 {item['people']} people")
                    msg_lines.append("")

                msg_lines.append(
                    f"💰 Total: ${data['data']['amount_in_cents']/100:.2f} USD"
                )

                send_whatsapp_notifications("\n".join(msg_lines))

                return render_template(
                    "payment_success.html",
                    cart=pending["cart"],
                    total=data["data"]["amount_in_cents"] / 100
                )

            # =================================================
            #  CASO 2 — SINGLE TOUR
            # =================================================
            else:

                booking = Booking(
                    tour_id=pending["tour_id"],
                    date=pending["date"],
                    people=pending["people"],
                    email=pending["email"]
                )

                db.session.add(booking)
                db.session.commit()

                # buscar nombre del tour
                tour = next(
                    (t for t in tours_data if t["id"] == pending["tour_id"]),
                    None
                )

                # ==============================
                #  WhatsApp automático (single)
                # ==============================
                tour_name = tour["name"] if tour else "Tour"

                message = (
                    "✅ NEW PAID BOOKING\n\n"
                    f"🏔 Tour: {tour_name}\n"
                    f"📅 Date: {pending['date']}\n"
                    f"👥 People: {pending['people']}\n"
                    f"📧 Email: {pending['email']}\n"
                    f"💰 Total: ${data['data']['amount_in_cents']/100:.2f} USD"
                )

                send_whatsapp_notifications(message)

                return render_template(
                    "payment_success.html",
                    tour=tour,
                    booking=pending,
                    total=data["data"]["amount_in_cents"] / 100
                )

    return render_template("payment_success.html")


@app.route("/cart") #ruta al carrito
def cart_page():
    return render_template("cart.html")


@app.route("/wompi-webhook", methods=["POST"])
def wompi_webhook():
    data = request.json

    if data.get("estado") == "APROBADO":
        pass
        # guardar reserva en SQLite


@app.route("/checkout")
def checkout():
    tour_id = request.args.get("tour_id")
    date = request.args.get("date")
    people = request.args.get("people")

    return render_template(
        "checkout.html",
        tour_id=tour_id,
        date=date,
        people=people
    )


# Punto de entrada de la aplicación
if __name__ == "__main__":
    app.run(debug=True)
