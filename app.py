```python
import json, os, uuid
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, redirect
import requests

load_dotenv()

app = Flask(__name__)

# =========================
# ENV VARIABLES
# =========================
WOMPI_PUBLIC_KEY = os.getenv("WOMPI_PUBLIC_KEY")
WOMPI_PRIVATE_KEY = os.getenv("WOMPI_PRIVATE_KEY")
WOMPI_API = os.getenv("WOMPI_API")

# =========================
# FILE HANDLERS
# =========================
def load_tours():
    with open("data/tours.json", "r", encoding="utf-8") as f:
        return json.load(f)

def load_bookings():
    try:
        with open("data/bookings.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_bookings(bookings):
    with open("data/bookings.json", "w", encoding="utf-8") as f:
        json.dump(bookings, f, indent=2)

# =========================
# WHATSAPP
# =========================
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
                    params={"phone": number, "text": message},
                    timeout=5
                )
            except Exception as e:
                print("WhatsApp error:", e)

# =========================
# ROUTES
# =========================
@app.route("/")
def home():
    return render_template("index.html", tours=load_tours())

@app.route("/tours")
def tours():
    return render_template("tours.html", tours=load_tours())

@app.route("/tours/<int:tour_id>")
def tour_detail(tour_id):
    tours_data = load_tours()
    tour = next((t for t in tours_data if t["id"] == tour_id), None)

    if not tour:
        return "Tour not found", 404

    return render_template("tour_detail.html", tour=tour)

@app.route("/calendar")
def calendar():
    return render_template("calendar.html")

@app.route("/gallery")
def gallery():
    return render_template("gallery.html")

@app.route("/cart")
def cart_page():
    return render_template("cart.html")

@app.route("/checkout")
def checkout():
    return render_template(
        "checkout.html",
        tour_id=request.args.get("tour_id"),
        date=request.args.get("date"),
        people=request.args.get("people")
    )

# =========================
# BOOKINGS API
# =========================
@app.route("/api/book", methods=['POST'])
def book():
    data = request.json

    bookings = load_bookings()

    bookings.append({
        "tour_id": data["tour_id"],
        "date": data["date"],
        "name": data["name"],
        "email": data["email"]
    })

    save_bookings(bookings)

    return jsonify({"status": "ok"})

@app.route("/api/bookings/<int:tour_id>")
def get_bookings(tour_id):
    bookings = load_bookings()

    filtered = [b for b in bookings if b["tour_id"] == tour_id]

    return jsonify([
        {"date": b["date"]}
        for b in filtered
    ])

# =========================
# PAYMENT
# =========================
@app.route("/create-payment", methods=["POST"])
def create_payment():

    tours_data = load_tours()
    cart_data = request.form.get("cart_data")

    # MULTI TOUR
    if cart_data:
        cart = json.loads(cart_data)
        total = sum(item.get("price", 0) for item in cart)

        reference_payload = json.dumps({"cart": cart})
        product_name = "Cotuza Tours – Multi-Tour Booking"
        product_desc = f"{len(cart)} tours"

    # SINGLE TOUR
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

    # TOKEN
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
        return jsonify({"error": "No token"}), 400

    # CREATE PAYMENT
    payment_response = requests.post(
        f"{WOMPI_API}/EnlacePago",
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

    url_pago = payment_response.json().get("urlEnlace")

    return redirect(url_pago)

# =========================
# PAYMENT SUCCESS
# =========================
@app.route("/payment-success")
def payment_success():

    transaction_id = request.args.get("id")

    if not transaction_id:
        return render_template("payment_success.html")

    headers = {"Authorization": f"Bearer {WOMPI_PRIVATE_KEY}"}

    r = requests.get(f"{WOMPI_API}/transactions/{transaction_id}", headers=headers)
    data = r.json()

    if data.get("data", {}).get("status") == "APPROVED":

        reference_data = data["data"].get("reference")

        if reference_data:
            pending = json.loads(reference_data)
            bookings = load_bookings()

            # CART
            if "cart" in pending:
                for item in pending["cart"]:
                    bookings.append({
                        "tour_id": item["tour_id"],
                        "date": item["date"],
                        "people": item["people"],
                        "email": pending["email"]
                    })

            # SINGLE
            else:
                bookings.append({
                    "tour_id": pending["tour_id"],
                    "date": pending["date"],
                    "people": pending["people"],
                    "email": pending["email"]
                })

            save_bookings(bookings)

            send_whatsapp_notifications("✅ NEW PAID BOOKING")

    return render_template("payment_success.html")

# =========================
# RUN
# =========================
if __name__ == "__main__":
    app.run(debug=True)
```
