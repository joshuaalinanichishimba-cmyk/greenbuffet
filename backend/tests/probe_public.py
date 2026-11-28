"""An end-to-end run through the customer-facing stages, against a real server.

This walks the whole journey the way a customer and then a cashier would: read
the menu with no token, place a delivery order, watch it be refused for being
under the minimum, place a good one, accept it, send a rider, take the money at
the till, and check that the points, the stock and the books all moved.

Run with the server up:
    python -m tests.probe_public
"""
import json
import os
import sys
import uuid

import requests

from safety import validate_test_target

validate_test_target()
BASE = os.environ.get("GB_BASE", "http://127.0.0.1:18000/api/v1")
EMAIL = os.environ.get("GB_EMAIL", "owner@greenbuffet.zm")
PASSWORD = os.environ.get("GB_PASSWORD", "greenbuffet2026")

passed, failed = 0, 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {label}")
    else:
        failed += 1
        print(f"  FAIL  {label}  {detail}")


def call(method: str, path: str, token: str | None = None, **kwargs):
    headers = kwargs.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if method != "GET":
        headers["Idempotency-Key"] = str(uuid.uuid4())
    return requests.request(method, f"{BASE}{path}", headers=headers, timeout=20, **kwargs)


def main() -> int:
    print("\n== The menu, with no token at all")
    menu = call("GET", "/public/menu")
    check("the menu is public", menu.status_code == 200, menu.text[:120])
    categories = menu.json()["categories"]
    check("the menu has food on it", len(categories) > 0)
    product = None
    for category in categories:
        for item in category["products"]:
            if item["is_available"] and not item["groups"]:
                product = item
                break
        if product:
            break
    check("found a simple item to order", product is not None)
    if not product:
        return 1
    print(f"        using {product['name']} at {product['price_ngwee']} ngwee")

    body = json.dumps(menu.json())
    check("no cost prices leak into the public menu", "cost_ngwee" not in body)
    check("no recipes leak into the public menu", "recipe" not in body)
    check("no stock levels leak into the public menu", "stock" not in body.lower())

    print("\n== Signing in as staff")
    signin = call("POST", "/auth/login", json={"email": EMAIL, "password": PASSWORD})
    if signin.status_code != 200:
        print(f"  Cannot sign in: {signin.status_code} {signin.text[:200]}")
        return 1
    token = signin.json()["token"]

    shop = call("GET", "/public/shop").json()
    zone = next((z for z in shop["zones"] if z["minimum_ngwee"] > 0), shop["zones"][0])
    print(f"        delivering to {zone['name']}, fee {zone['fee_ngwee']}, minimum {zone['minimum_ngwee']}")

    phone = "097" + str(uuid.uuid4().int)[:7]
    one = {"product_id": product["id"], "quantity": 1, "options": [], "note": ""}

    print("\n== What the website refuses")
    under = call("POST", "/public/orders", json={
        "lines": [one], "customer_name": "Probe Customer", "customer_phone": phone,
        "fulfilment": "delivery", "zone_id": zone["id"], "address": "12 Probe Road",
    })
    if product["price_ngwee"] < zone["minimum_ngwee"]:
        check("an order under the area's minimum is refused", under.status_code == 422, under.text[:160])
    else:
        check("a valid delivery is taken", under.status_code == 201, under.text[:160])

    no_address = call("POST", "/public/orders", json={
        "lines": [one], "customer_name": "Probe Customer", "customer_phone": phone,
        "fulfilment": "delivery", "zone_id": zone["id"], "address": "",
    })
    check("a delivery with no address is refused", no_address.status_code == 422, no_address.text[:160])

    no_phone = call("POST", "/public/orders", json={
        "lines": [one], "customer_name": "Probe Customer", "customer_phone": "123",
    })
    check("a bad phone number is refused", no_phone.status_code == 422, no_phone.text[:160])

    bad_item = call("POST", "/public/orders", json={
        "lines": [{"product_id": "not-a-real-product", "quantity": 1, "options": [], "note": ""}],
        "customer_name": "Probe Customer", "customer_phone": phone,
    })
    check("an item that is not on the menu is refused", bad_item.status_code == 422, bad_item.text[:160])

    print("\n== Placing a real collection order")
    quantity = max(1, -(-zone["minimum_ngwee"] // max(product["price_ngwee"], 1)))
    lines = [{"product_id": product["id"], "quantity": quantity, "options": [], "note": "no chilli"}]
    placed = call("POST", "/public/orders", json={
        "lines": lines, "customer_name": "Probe Customer", "customer_phone": phone,
        "fulfilment": "delivery", "zone_id": zone["id"], "address": "12 Probe Road, Riverside",
        "directions": "Green gate", "note": "Probe order",
    })
    check("the order is accepted by the website", placed.status_code == 201, placed.text[:200])
    if placed.status_code != 201:
        return 1
    order = placed.json()
    expected = product["price_ngwee"] * quantity + zone["fee_ngwee"]
    check("the total includes the delivery fee", order["total_ngwee"] == expected,
          f"{order['total_ngwee']} vs {expected}")

    print("\n== What the customer can see")
    track = call("GET", f"/public/orders/{order['token']}")
    check("the customer can track their own order", track.status_code == 200)
    check("tracking shows it as placed", track.json()["status"] == "placed")
    stranger = call("GET", "/public/orders/" + "x" * 30)
    check("a wrong token finds nothing", stranger.status_code == 404)

    print("\n== The restaurant accepts it")
    waiting = call("GET", "/customers/online", token=token).json()
    mine = next((o for o in waiting if o["number"] == order["number"]), None)
    check("the order is on the staff screen", mine is not None)
    accepted = call("POST", f"/customers/online/{mine['id']}/accept", token=token, json={"minutes": 25})
    check("staff can accept it", accepted.status_code == 200, accepted.text[:160])
    check("accepting starts the kitchen", accepted.json()["track_status"] == "cooking")
    again = call("POST", f"/customers/online/{mine['id']}/accept", token=token, json={"minutes": 25})
    check("accepting twice is refused", again.status_code == 409, again.text[:120])

    board = call("GET", "/kitchen/tickets", token=token)
    check("the kitchen board has the order", order["number"] in board.text, board.text[:120])

    print("\n== Out for delivery")
    rider = call("POST", f"/customers/online/{mine['id']}/rider", token=token,
                 json={"rider_name": "Probe Rider", "rider_phone": "0966000111"})
    check("a rider can be given the order", rider.status_code == 200, rider.text[:160])
    check("it is marked on the way", rider.json()["track_status"] == "on_the_way")
    track = call("GET", f"/public/orders/{order['token']}").json()
    check("the customer sees it on the way", track["status"] == "on_the_way")

    print("\n== Paying for it at the till")
    shift = call("GET", "/sales/shifts/current", token=token)
    if shift.status_code != 200 or not shift.json():
        call("POST", "/sales/shifts", token=token, json={"float_ngwee": 20000})
    full = call("GET", f"/sales/orders/{mine['id']}", token=token).json()
    pay = call("POST", f"/sales/orders/{mine['id']}/payments", token=token,
               json={"method": "cash", "amount_ngwee": full["total_ngwee"],
                     "tendered_ngwee": full["total_ngwee"]})
    check("the delivery can be paid for at the till", pay.status_code == 200, pay.text[:200])
    check("it is now a paid sale", pay.json()["status"] == "paid")

    print("\n== Points")
    customer = call("GET", f"/customers/by-phone/{phone}", token=token)
    check("the customer was remembered", customer.status_code == 200, customer.text[:160])
    food = full["total_ngwee"] - zone["fee_ngwee"]
    earned = customer.json()["points"]
    check("points are earned on food only, not delivery", earned == food // 100,
          f"{earned} points for {food} ngwee of food")
    public_points = call("GET", f"/public/points/{phone}").json()
    check("the customer can check their own points", public_points["points"] == earned)

    print("\n== The books still balance")
    trial = call("GET", "/books/trial-balance", token=token)
    if trial.status_code == 200:
        data = trial.json()
        check("the trial balance is still zero",
              data.get("balanced") is True
              and data["total_debit_ngwee"] == data["total_credit_ngwee"],
              f"{data.get('total_debit_ngwee')} against {data.get('total_credit_ngwee')}")
    delivery_income = call("GET", "/books/accounts", token=token)
    if delivery_income.status_code == 200:
        codes = [a["code"] for a in delivery_income.json()]
        check("delivery charges have their own account", "4200" in codes)
        check("customer deposits have their own account", "2150" in codes)

    print("\n== Messages were written down")
    queued = call("GET", "/customers/messages?state=queued", token=token)
    check("messages are queued for the customer", queued.status_code == 200)
    about_this = [m for m in queued.json() if m["reference"] == order["number"]]
    check("there is a message about this order", len(about_this) >= 2,
          f"{len(about_this)} messages")

    print("\n== Catering")
    booking = call("POST", "/customers/bookings", token=token, json={
        "customer_name": "Probe Functions", "customer_phone": "0977123456",
        "guests": 50, "venue": "Probe Hall", "details": "Buffet for fifty",
        "quote_ngwee": 500000, "deposit_due_ngwee": 250000,
    })
    check("a function can be quoted", booking.status_code == 201, booking.text[:200])
    if booking.status_code == 201:
        bid = booking.json()["id"]
        deposit = call("POST", f"/customers/bookings/{bid}/deposit", token=token,
                       json={"amount_ngwee": 250000, "method": "cash"})
        check("a deposit can be taken", deposit.status_code == 200, deposit.text[:200])
        check("the deposit confirms the booking", deposit.json()["status"] == "confirmed")
        too_much = call("POST", f"/customers/bookings/{bid}/settle", token=token,
                        json={"amount_ngwee": 100, "method": "cash"})
        check("the balance cannot be settled before delivery", too_much.status_code == 409,
              too_much.text[:120])
        done = call("POST", f"/customers/bookings/{bid}/delivered", token=token)
        check("the function can be delivered", done.status_code == 200, done.text[:200])
        check("the balance is what is left", done.json()["balance_ngwee"] == 250000,
              str(done.json()["balance_ngwee"]))
        settle = call("POST", f"/customers/bookings/{bid}/settle", token=token,
                      json={"amount_ngwee": 250000, "method": "bank"})
        if settle.status_code != 200:
            settle = call("POST", f"/customers/bookings/{bid}/settle", token=token,
                          json={"amount_ngwee": 250000, "method": "cash"})
        check("the balance can be paid", settle.status_code == 200, settle.text[:200])
        check("nothing is left owing", settle.json()["balance_ngwee"] == 0)

    trial = call("GET", "/books/trial-balance", token=token)
    if trial.status_code == 200:
        data = trial.json()
        check("the books still balance after catering",
              data.get("balanced") is True
              and data["total_debit_ngwee"] == data["total_credit_ngwee"],
              f"{data.get('total_debit_ngwee')} against {data.get('total_credit_ngwee')}")

    print(f"\n  {passed} passed, {failed} failed\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
