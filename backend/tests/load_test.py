"""A busy lunch, simulated.

Not a unit test — run it by hand against a running backend when you want to
know whether the system holds up:

    cd backend
    .\\.venv\\Scripts\\python.exe tests\\load_test.py

It takes real orders and real payments, so run it on a test database or expect
the day's figures to include them.
"""

import json, statistics, time, threading, uuid
import requests

B = "http://localhost:8000/api/v1"
def login(email, password):
    return requests.post(f"{B}/auth/login", json={"email": email, "password": password}, timeout=20).json()["token"]

owner = login("owner@greenbuffet.zm", "greenbuffet2026")
H = lambda t: {"Authorization": f"Bearer {t}"}

products = requests.get(f"{B}/menu/products", headers=H(owner), timeout=20).json()
simple = [p for p in products if not p["option_groups"] and p["is_available"]][:4]
built = next(p for p in products if p["option_groups"])
required = [g for g in built["option_groups"] if g["min_select"] > 0]
choices = [{"option_item_id": g["items"][0]["id"]} for g in required]

shift = requests.get(f"{B}/sales/shifts/current", headers=H(owner), timeout=20).json()
if not shift or not shift["is_open"]:
    requests.post(f"{B}/sales/shifts", headers=H(owner), json={"float_ngwee": 50000}, timeout=20)

timings, errors = [], []
lock = threading.Lock()

def one_sale(n):
    try:
        start = time.perf_counter()
        key = str(uuid.uuid4())
        lines = [{"product_id": simple[n % len(simple)]["id"], "quantity": 1 + n % 3}]
        if n % 3 == 0:
            lines.append({"product_id": built["id"], "quantity": 1, "options": choices})
        order = requests.post(f"{B}/sales/orders", headers={**H(owner), "Idempotency-Key": key},
                              json={"lines": lines}, timeout=30).json()
        if "id" not in order:
            with lock: errors.append(("order", order)); return
        paid = requests.post(f"{B}/sales/orders/{order['id']}/payments",
                             headers={**H(owner), "Idempotency-Key": str(uuid.uuid4())},
                             json={"method": "cash", "amount_ngwee": order["total_ngwee"]}, timeout=30).json()
        if paid.get("status") != "paid":
            with lock: errors.append(("payment", paid)); return
        with lock: timings.append(time.perf_counter() - start)
    except Exception as problem:
        with lock: errors.append(("exception", str(problem)[:120]))

def reader(path, count, bucket):
    for _ in range(count):
        start = time.perf_counter()
        r = requests.get(f"{B}{path}", headers=H(owner), timeout=30)
        with lock:
            bucket.append((time.perf_counter() - start, r.status_code))

print("A busy lunch: 60 sales from 6 tills, with the kitchen board and dashboard open\n")
board, dash = [], []
began = time.perf_counter()
threads = [threading.Thread(target=reader, args=("/kitchen/tickets", 30, board)),
           threading.Thread(target=reader, args=("/reports/dashboard?days=7", 10, dash))]
for n in range(60):
    threads.append(threading.Thread(target=one_sale, args=(n,)))
for t in threads: t.start()
for t in threads: t.join()
elapsed = time.perf_counter() - began

def summary(name, values):
    if not values: return f"  {name}: nothing recorded"
    values = sorted(values)
    worst = values[int(len(values) * 0.95) - 1]
    return (f"  {name}: {len(values)} calls, median {statistics.median(values)*1000:.0f} ms, "
            f"95th {worst*1000:.0f} ms, slowest {values[-1]*1000:.0f} ms")

print(f"  finished in {elapsed:.1f} s  ({len(timings)/elapsed:.1f} complete sales a second)")
print(summary("order and payment", timings))
print(summary("kitchen board", [t for t, _ in board]))
print(summary("dashboard", [t for t, _ in dash]))
print(f"  board responses: {sorted({c for _, c in board})}, dashboard: {sorted({c for _, c in dash})}")
print(f"  failures: {len(errors)}")
for e in errors[:3]: print("   ", e)

tb = requests.get(f"{B}/books/trial-balance", headers=H(owner), timeout=30).json()
bs = requests.get(f"{B}/books/balance-sheet", headers=H(owner), timeout=30).json()
print(f"\n  after the rush — trial balance: {'balanced' if tb['balanced'] else 'OUT'}, "
      f"balance sheet: {'balanced' if bs['balanced'] else 'OUT by ' + str(bs['difference_ngwee'])}")
orders = requests.get(f"{B}/sales/orders?today=true", headers=H(owner), timeout=30).json()
numbers = [o["number"] for o in orders]
print(f"  orders today: {len(numbers)}, duplicate numbers: {len(numbers) - len(set(numbers))}")
