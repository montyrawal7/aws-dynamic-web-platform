import os
import sqlite3
from datetime import datetime
from uuid import uuid4

import boto3
from flask import Flask, render_template, request, redirect, url_for, flash

APP_DB = os.environ.get("APP_DB_PATH", "orders.db")
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "").strip()
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-change-me")

PRODUCTS = [
    {"id": "p1", "name": "Wireless Earbuds", "price": 49.99},
    {"id": "p2", "name": "Portable Charger", "price": 29.99},
    {"id": "p3", "name": "Smart LED Bulb", "price": 14.99},
    {"id": "p4", "name": "Laptop Stand", "price": 24.99},
]

def init_db():
    with sqlite3.connect(APP_DB) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                customer_name TEXT NOT NULL,
                customer_email TEXT NOT NULL,
                items_json TEXT NOT NULL,
                total_amount REAL NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()

def publish_confirmation(order_id: str, customer_name: str, customer_email: str, total: float, items_summary: str):
    # App runs fine even without SNS configured locally.
    if not SNS_TOPIC_ARN:
        return

    sns = boto3.client("sns", region_name=AWS_REGION)

    subject = f"Order Confirmed: {order_id}"
    message = (
        f"Hi {customer_name},\n\n"
        f"Your order is confirmed.\n\n"
        f"Order ID: {order_id}\n"
        f"Email: {customer_email}\n"
        f"Items:\n{items_summary}\n\n"
        f"Total: ${total:.2f}\n"
        f"Time: {datetime.utcnow().isoformat()}Z\n\n"
        f"Thanks!"
    )

    sns.publish(TopicArn=SNS_TOPIC_ARN, Subject=subject, Message=message)

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html", products=PRODUCTS)

@app.route("/order", methods=["POST"])
def place_order():
    customer_name = request.form.get("customer_name", "").strip()
    customer_email = request.form.get("customer_email", "").strip()

    if not customer_name or not customer_email:
        flash("Please enter your name and email.")
        return redirect(url_for("index"))

    cart = []
    total = 0.0
    lines = []

    for p in PRODUCTS:
        qty_raw = request.form.get(f"qty_{p['id']}", "0").strip()
        try:
            qty = int(qty_raw)
        except ValueError:
            qty = 0

        if qty > 0:
            line_total = qty * p["price"]
            total += line_total
            cart.append(
                {"id": p["id"], "name": p["name"], "price": p["price"], "qty": qty, "line_total": line_total}
            )
            lines.append(f"- {p['name']} x{qty} = ${line_total:.2f}")

    if not cart:
        flash("Please select at least one product quantity > 0.")
        return redirect(url_for("index"))

    order_id = f"ORD-{uuid4().hex[:8].upper()}"
    created_at = datetime.utcnow().isoformat() + "Z"

    with sqlite3.connect(APP_DB) as conn:
        conn.execute(
            "INSERT INTO orders (order_id, customer_name, customer_email, items_json, total_amount, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (order_id, customer_name, customer_email, str(cart), total, created_at),
        )
        conn.commit()

    publish_confirmation(order_id, customer_name, customer_email, total, "\n".join(lines))

    return render_template("confirm.html", order_id=order_id, name=customer_name, email=customer_email, cart=cart, total=total)

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=True)
