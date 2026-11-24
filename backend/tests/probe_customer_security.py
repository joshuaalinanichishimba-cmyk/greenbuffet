"""Who may do what on the customer-facing routes.

Stage 12 found that a cashier could read every stored document, which nobody
had thought to check. These stages add money (deposits), a customer list and a
public API, so the same question is asked again here, deliberately and in
writing: for each new thing, who should be refused?

Run with the server up:
    python -m tests.probe_customer_security
"""
import os
import sys
import uuid

import requests

BASE = os.environ.get("GB_BASE", "http://localhost:8000/api/v1")
OWNER = (os.environ.get("GB_EMAIL", "owner@greenbuffet.zm"), os.environ.get("GB_PASSWORD", "greenbuffet2026"))

passed, failed = 0, 0


def check(label, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {label}")
    else:
        failed += 1
        print(f"  FAIL  {label}  {detail}")


def call(method, path, token=None, **kwargs):
    headers = kwargs.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if method != "GET":
        headers["Idempotency-Key"] = str(uuid.uuid4())
    return requests.request(method, f"{BASE}{path}", headers=headers, timeout=20, **kwargs)


def sign_in(email, password):
    r = call("POST", "/auth/login", json={"email": email, "password": password})
    return r.json().get("token") if r.status_code == 200 else None


def main():
    owner = sign_in(*OWNER)
    if not owner:
        print("Cannot sign in as the owner.")
        return 1

    print("\n== A cashier account")
    email = f"probe-cashier-{uuid.uuid4().hex[:6]}@greenbuffet.zm"
    made = call("POST", "/admin/users", token=owner,
                json={"name": "Probe Cashier", "email": email, "role_id": "cashier"})
    if made.status_code != 201:
        print(f"  Could not make a cashier: {made.status_code} {made.text[:160]}")
        return 1
    temporary = made.json()["temporary_password"]
    cashier = sign_in(email, temporary)
    if cashier:
        call("POST", "/auth/change-password", token=cashier,
             json={"current_password": temporary, "new_password": "ProbeCashier#2026"})
        cashier = sign_in(email, "ProbeCashier#2026")
    check("the cashier can sign in", bool(cashier))

    print("\n== What a cashier may do")
    check("sees customers at the till", call("GET", "/customers", token=cashier).status_code == 200)
    order = call("POST", "/sales/orders", token=cashier, json={"order_type": "delivery", "lines": []})
    check("cannot take a delivery order (a counter-only point of sale)", order.status_code in (409, 422), f"{order.status_code}")

    print("\n== What a cashier may not do")

    people = call("GET", "/customers", token=cashier).json()
    if people:
        adjust = call("POST", f"/customers/{people[0]['id']}/stamps", token=cashier,
                      json={"points": 8, "reason": "probe"})
        check("cannot fill their own stamp card", adjust.status_code == 403, f"{adjust.status_code}")
        block = call("PATCH", f"/customers/{people[0]['id']}", token=cashier, json={"is_blocked": True})
        check("cannot block a customer", block.status_code == 403, f"{block.status_code}")


    print("\n== The demo's screens: what a cashier may not do")
    promo = call("POST", "/dashboard/promotions", token=cashier,
                 json={"code": "CASHIER50", "kind": "percent", "value": 50})
    check("cannot invent a promotion code", promo.status_code == 403, f"{promo.status_code}")
    listing = call("GET", "/dashboard/promotions", token=owner).json()
    if listing:
        stop = call("POST", f"/dashboard/promotions/{listing[0]['id']}/toggle", token=cashier)
        check("cannot stop or start a promotion", stop.status_code == 403, f"{stop.status_code}")
    analytics = call("GET", "/dashboard/analytics", token=cashier)
    check("cannot read sales analytics", analytics.status_code == 403, f"{analytics.status_code}")
    prep = call("POST", "/dashboard/service/prep", token=cashier, json={"minutes": 99})
    check("cannot change the kitchen's base time", prep.status_code == 403, f"{prep.status_code}")
    check("can look up a promo code at the till",
          call("GET", "/dashboard/promotions/check/NOSUCH?food_ngwee=1000", token=cashier).status_code == 422)
    check("can write down feedback",
          call("POST", "/dashboard/feedback", token=cashier, json={"rating": 5, "comment": "probe"}).status_code == 201)

    print("\n== Settings refuse what nothing reads")
    bad = call("PUT", "/settings", token=owner, json={"values": {"loyalty.stamps_neded": "3"}})
    check("a misspelt setting is refused", bad.status_code == 422, f"{bad.status_code}")
    bad = call("PUT", "/settings", token=owner, json={"values": {"loyalty.stamps_needed": "0"}})
    check("a stamp card of nought is refused", bad.status_code == 422, f"{bad.status_code}")

    print("\n== What a stranger with no token may do")
    print("  (nothing: this system has no public side at all)")

    print("\n== What a stranger may not do")
    for label, path, method, body in [
        ("list customers", "/customers", "GET", None),
        ("read the till's orders", "/sales/orders", "GET", None),
        ("read the books", "/books/trial-balance", "GET", None),
        ("read the overview", "/dashboard/overview", "GET", None),
        ("read the payments", "/dashboard/payments", "GET", None),
        ("read the end of day", "/dashboard/end-of-day", "GET", None),
        ("read the promotions", "/dashboard/promotions", "GET", None),
        ("read stored files", "/settings/files", "GET", None),
    ]:
        r = call(method, path, json=body) if body else call(method, path)
        check(f"cannot {label}", r.status_code in (401, 403), f"{r.status_code}")

    print("\n== Customer ordering is gone (stage 20)")
    for label, path in [
        ("the deliveries board", "/customers/deliveries"),
        ("the message outbox", "/customers/messages"),
        ("function bookings", "/customers/bookings"),
        ("delivery areas", "/customers/zones"),
    ]:
        r = call("GET", path, token=owner)
        check(f"{label} no longer exists", r.status_code in (404, 405, 422), f"{r.status_code}")

    print("\n== The public API is gone")
    for label, path in [
        ("the customer menu", "/public/menu"),
        ("the shop details", "/public/shop"),
        ("order tracking", "/public/orders/anything"),
        ("the photo route", "/public/photo/anything"),
    ]:
        r = call("GET", path)
        check(f"{label} no longer exists", r.status_code == 404, f"{r.status_code}")

    print("\n== Tidying up")
    call("PATCH", f"/admin/users/{made.json()['id']}", token=owner, json={"is_active": False})

    print(f"\n  {passed} passed, {failed} failed\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
