from flask import Flask, request, jsonify
import requests
import re
from datetime import datetime

app = Flask(__name__)

API_URL = """https://exam.sanand.workers.dev/questionData?email=24f1000754%40ds.study.iitm.ac.in&quizSign=Nw9hunMU2VAVVWIhiXALfErlHEvsf8Fgjea%2B%2B42duyYHO2%2BedRyhnwtUfizXIoN7th6mvnvyBx9cjhfBXzdJKmEyjudbxThYw%2Bj6xjz6zRhLJ3fYMEw95tp6xeyNHzwUyKYd9pBhFqecBcDY6qDAg7aZNaYhIkWw%2FbTq%2B11hAtD6HtNFrMb8ikbBC4ZfRJ8Dvz3WQ6HMVqf1P8EYyyaFlV%2FlY8Nf4Shf2ubUJ4KsHkPdhzXwsN0daPf8ZaGRlCXRexUM4kucVTRphwlFJ1y%2FnTieoxK%2BB2WpJxc3k0G6ib7t6y3%2F2LdgoTYYF9hHJZjvTk2361FK6v3CaI7GSnyT2A%3D%3D&questionId=q-ledger-agent-server&path=%2Forders&page=1"""

RATES = {
    "USD": 1,
    "EUR": 1.13,
    "INR": 0.01142
}

MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12
}


def get_all_orders():
    all_orders = []

    session = requests.Session()

    response = session.get(
        API_URL,
        params={"page": 1},
        timeout=30
    )
    response.raise_for_status()

    data = response.json()
    total_pages = data["pages"]

    print("Total pages:", total_pages)

    all_orders.extend(data["orders"])

    for page in range(2, total_pages + 1):

        print(f"Fetching page {page}/{total_pages}")

        for attempt in range(3):

            try:
                response = session.get(
                    API_URL,
                    params={"page": page},
                    timeout=30
                )

                response.raise_for_status()

                page_data = response.json()
                all_orders.extend(page_data["orders"])

                break

            except requests.exceptions.RequestException as e:

                print(
                    f"Page {page} failed "
                    f"(attempt {attempt + 1}/3): {e}"
                )

                if attempt == 2:
                    raise

    print("Total rows fetched:", len(all_orders))

    return all_orders


def clean_orders(orders):
    latest = {}

    for order in orders:

        order_id = order["id"]

        if order_id not in latest:
            latest[order_id] = order

        else:
            if order["updated_at"] > latest[order_id]["updated_at"]:
                latest[order_id] = order

    return list(latest.values())


def get_date(order):
    return datetime.fromisoformat(
        order["created_at"].replace("Z", "+00:00")
    )


def convert_to_usd(amount, currency):
    return amount * RATES.get(currency, 1)


def parse_question(question):
    q = question.lower()

    result = {
        "metric": None,
        "region": None,
        "product": None,
        "customer": None,
        "month": None,
        "year": None,
        "aggregation": "sum"
    }

    # -------------------------
    # Metric / intent
    # -------------------------

    if "refund" in q or "refunded" in q:
        result["metric"] = "refund"

    elif "revenue" in q or "sales" in q or "sale" in q:
        result["metric"] = "revenue"

    elif "quantity" in q or "units" in q:
        result["metric"] = "quantity"

    elif "order" in q or "orders" in q:
        result["metric"] = "orders"

    else:
        result["metric"] = "revenue"

    # -------------------------
    # Aggregation
    # -------------------------

    if any(word in q for word in [
        "how many",
        "number of",
        "count",
        "no. of"
    ]):
        result["aggregation"] = "count"

    # -------------------------
    # Region
    # -------------------------

    regions = [
        "north",
        "south",
        "east",
        "west",
        "central"
    ]

    for region in regions:
        if re.search(r"\b" + region + r"\b", q):
            result["region"] = region
            break

    # -------------------------
    # Product
    # -------------------------

    products = sorted(
        set(
            str(o["product"]).lower()
            for o in orders
        ),
        key=len,
        reverse=True
    )

    for product in products:
        if product in q:
            result["product"] = product
            break

    # -------------------------
    # Customer
    # -------------------------

    customers = sorted(
        set(
            str(o["customer"]).lower()
            for o in orders
        ),
        key=len,
        reverse=True
    )

    for customer in customers:
        if customer in q:
            result["customer"] = customer
            break

    # -------------------------
    # Month
    # -------------------------

    for month_name, month_number in MONTHS.items():

        if month_name in q:
            result["month"] = month_number
            break

    # -------------------------
    # Year
    # -------------------------

    years = re.findall(r"\b20\d{2}\b", q)

    if years:
        result["year"] = int(years[0])

    return result


def calculate(parsed):
    metric = parsed["metric"]

    selected = []

    for order in orders:

        date = get_date(order)

        # Region
        if parsed["region"]:
            if order["region"].lower() != parsed["region"]:
                continue

        # Product
        if parsed["product"]:
            if order["product"].lower() != parsed["product"]:
                continue

        # Customer
        if parsed["customer"]:
            if order["customer"].lower() != parsed["customer"]:
                continue

        # Month
        if parsed["month"]:
            if date.month != parsed["month"]:
                continue

        # Year
        if parsed["year"]:
            if date.year != parsed["year"]:
                continue

        selected.append(order)

    # -------------------------
    # Revenue
    # -------------------------

    if metric == "revenue":

        total = 0

        for order in selected:

            if order["status"] != "paid":
                continue

            total += convert_to_usd(
                order["amount"],
                order["currency"]
            )

        return round(total, 2)

    # -------------------------
    # Refunds
    # -------------------------

    if metric == "refund":

        total = 0

        for order in selected:

            if order["status"] != "refunded":
                continue

            total += convert_to_usd(
                order["amount"],
                order["currency"]
            )

        return round(total, 2)

    # -------------------------
    # Quantity
    # -------------------------

    if metric == "quantity":

        total = 0

        for order in selected:

            if order["status"] == "paid":
                total += order["qty"]

        return total

    # -------------------------
    # Orders
    # -------------------------

    if metric == "orders":

        return sum(
            1
            for order in selected
            if order["status"] == "paid"
        )

    return 0


# =================================
# LOAD DATA
# =================================

print("Loading ledger data...")

orders = get_all_orders()

orders = clean_orders(orders)

print("Unique orders:", len(orders))

print("Ledger loaded successfully!")


# =================================
# API
# =================================

@app.route("/", methods=["GET"])
def home():

    return jsonify({
        "status": "Ledger Agent is running",
        "orders": len(orders)
    })


@app.route("/answer", methods=["POST"])
def answer():

    data = request.get_json()

    question = data.get("question", "")

    if not question:
        return jsonify({
            "answer": "Please provide a question."
        }), 400

    parsed = parse_question(question)

    print("Question:", question)
    print("Parsed:", parsed)

    result = calculate(parsed)

    return jsonify({
        "answer": result
    })


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000
    )