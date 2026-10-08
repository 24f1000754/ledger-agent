from flask import Flask, request, jsonify
import requests
import json
import re
import threading
from datetime import datetime, timezone, timedelta

app = Flask(__name__)

BASE = (
    "https://exam.sanand.workers.dev/questionData?email=24f1000754%40ds.study.iitm.ac.in"
    "&quizSign=Nw9hunMU2VAVVWIhiXALfErlHEvsf8Fgjea%2B%2B42duyYHO2%2BedRyhnwtUfizXIoN7th6mvnvyBx9cjhfBXzdJKmEyjudbxThYw%2Bj6xjz6zRhLJ3fYMEw95tp6xeyNHzwUyKYd9pBhFqecBcDY6qDAg7aZNaYhIkWw%2FbTq%2B11hAtD6HtNFrMb8ikbBC4ZfRJ8Dvz3WQ6HMVqf1P8EYyyaFlV%2FlY8Nf4Shf2ubUJ4KsHkPdhzXwsN0daPf8ZaGRlCXRexUM4kucVTRphwlFJ1y%2FnTieoxK%2BB2WpJxc3k0G6ib7t6y3%2F2LdgoTYYF9hHJZjvTk2361FK6v3CaI7GSnyT2A%3D%3D"
    "&questionId=q-ledger-agent-server"
)
EXPORT_URL = BASE + "&path=%2Fexport"
RATES_URL = BASE + "&path=%2Frates"

IST = timezone(timedelta(hours=5, minutes=30))  # business dates are Asia/Kolkata

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

DATA = {"orders": [], "rates": {}, "products": [], "customers": [], "regions": []}
LOCK = threading.Lock()


def ts(s):
    return datetime.fromisoformat(str(s).strip().replace("Z", "+00:00"))


def load_data():
    """Download everything once: /export gives all rows in one request."""
    rates = requests.get(RATES_URL, timeout=30).json()["usd_per_unit"]
    rates = {k.upper(): float(v) for k, v in rates.items()}

    r = requests.get(EXPORT_URL, timeout=60)
    r.raise_for_status()
    rows = [json.loads(line) for line in r.text.splitlines() if line.strip()]

    # Same id can repeat -> keep row with latest updated_at (compare as real datetimes!)
    latest = {}
    for o in rows:
        oid = o["id"]
        if oid not in latest or ts(o["updated_at"]) > ts(latest[oid]["updated_at"]):
            latest[oid] = o

    orders = []
    for o in latest.values():
        d = ts(o["created_at"]).astimezone(IST)
        cur = str(o["currency"]).strip().upper()
        orders.append({
            "id": o["id"],
            "customer": str(o["customer"]).strip(),
            "region": str(o["region"]).strip(),
            "product": str(o["product"]).strip(),
            "qty": float(o.get("qty") or 0),
            "usd": float(o["amount"]) * rates.get(cur, 1.0),
            "status": str(o["status"]).strip().lower(),
            "year": d.year,
            "month": d.month,
            "day": d.day,
        })

    with LOCK:
        DATA["orders"] = orders
        DATA["rates"] = rates
        DATA["products"] = sorted({o["product"] for o in orders}, key=len, reverse=True)
        DATA["customers"] = sorted({o["customer"] for o in orders}, key=len, reverse=True)
        DATA["regions"] = sorted({o["region"] for o in orders}, key=len, reverse=True)
    print("Loaded orders:", len(orders), "from rows:", len(rows))


def ensure_loaded():
    if not DATA["orders"]:
        load_data()


def parse(question):
    q = question.lower()
    p = {"region": None, "product": None, "customer": None,
         "year": None, "months": None, "q": q}

    for reg in DATA["regions"]:
        if re.search(r"\b" + re.escape(reg.lower()) + r"\b", q):
            p["region"] = reg
            break
    for prod in DATA["products"]:
        if re.search(r"\b" + re.escape(prod.lower()) + r"s?\b", q):
            p["product"] = prod
            break
    for cust in DATA["customers"]:
        if re.search(r"\b" + re.escape(cust.lower()) + r"\b", q):
            p["customer"] = cust
            break

    years = re.findall(r"\b(20\d{2})\b", q)
    if years:
        p["year"] = int(years[0])

    # Quarter, e.g. "Q2 2026"
    qm = re.search(r"\bq([1-4])\b", q)
    if qm:
        n = int(qm.group(1))
        p["months"] = {3 * n - 2, 3 * n - 1, 3 * n}
    else:
        found = []
        for name, num in MONTHS.items():
            if re.search(r"\b" + name + r"\b", q) and num not in found:
                # avoid "may" as verb when no year context: still accept, it's common in these questions
                found.append(num)
        if len(found) >= 2 and re.search(r"\b(between|from|to|through|-)\b", q):
            p["months"] = set(range(min(found), max(found) + 1))
        elif found:
            p["months"] = {found[0]}
    return p


def select(p, status=None):
    out = []
    for o in DATA["orders"]:
        if p["region"] and o["region"] != p["region"]:
            continue
        if p["product"] and o["product"] != p["product"]:
            continue
        if p["customer"] and o["customer"] != p["customer"]:
            continue
        if p["year"] and o["year"] != p["year"]:
            continue
        if p["months"] and o["month"] not in p["months"]:
            continue
        if status and o["status"] != status:
            continue
        out.append(o)
    return out


def top_by(rows, key, value):
    totals = {}
    for o in rows:
        totals[o[key]] = totals.get(o[key], 0) + value(o)
    if not totals:
        return None
    lowest = re.search(r"\b(least|lowest|fewest|minimum|min|worst|smallest)\b", ANSWER_CTX["q"])
    return (min if lowest else max)(totals, key=totals.get)


ANSWER_CTX = {"q": ""}


def answer(question):
    ensure_loaded()
    p = parse(question)
    q = p["q"]
    ANSWER_CTX["q"] = q

    is_refund = bool(re.search(r"refund", q))
    is_void = bool(re.search(r"\bvoid", q))
    status = "refunded" if is_refund else ("void" if is_void else "paid")
    is_avg = bool(re.search(r"\b(average|avg|mean|typical|per order)\b", q))
    # "On average, how many dollars..." is an average, not a count
    is_count = bool(re.search(r"\b(how many|count|number of)\b", q)) and not is_avg
    if re.search(r"how many (us )?(dollars|usd|\$)", q):
        is_count = False
    is_qty = bool(re.search(r"\b(units|quantity|qty|items sold)\b", q))
    is_top = bool(re.search(r"\b(which|what|who|top|most|highest|best|least|lowest|largest|biggest)\b", q))

    # ---- "Which product / customer / region ..." ----
    if is_top and not is_count or re.search(r"\bwhich\b", q):
        group = None
        if re.search(r"\bproducts?\b", q) and not p["product"]:
            group = "product"
        elif re.search(r"\bcustomers?\b", q) and not p["customer"]:
            group = "customer"
        elif re.search(r"\bregions?\b", q) and not p["region"]:
            group = "region"
        if group:
            rows = select(p, status)
            if is_qty:
                return top_by(rows, group, lambda o: o["qty"])
            if re.search(r"\b(orders|order count)\b", q) and not re.search(r"revenue|usd|sales|amount|value", q):
                return top_by(rows, group, lambda o: 1)
            return top_by(rows, group, lambda o: o["usd"])

    if re.search(r"\bunique|distinct\b", q) and re.search(r"customers?", q):
        return len({o["customer"] for o in select(p, status)})

    rows = select(p, status)

    if is_count and not is_qty:
        return len(rows)
    if is_qty:
        return round(sum(o["qty"] for o in rows), 2)
    total = sum(o["usd"] for o in rows)
    if is_avg:
        return round(total / len(rows), 2) if rows else 0
    return round(total, 2)


@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "ok", "orders_loaded": len(DATA["orders"])})


@app.route("/answer", methods=["POST", "OPTIONS"])
def answer_route():
    if request.method == "OPTIONS":
        return ("", 204)
    body = request.get_json(silent=True) or {}
    question = str(body.get("question", ""))
    try:
        return jsonify({"answer": answer(question)})
    except Exception as e:
        return jsonify({"answer": None, "error": str(e)}), 500


@app.after_request
def cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
    return resp


# Load data as soon as the server starts (not on the first question)
try:
    load_data()
except Exception as e:
    print("Initial load failed, will retry on first request:", e)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
