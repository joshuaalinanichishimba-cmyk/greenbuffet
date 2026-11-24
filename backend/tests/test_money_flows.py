"""Money flows at the till, end to end, against a running test server.

    python -m pytest tests/test_money_flows.py

Phase 0 baseline (what already worked must keep working) and the Phase 1
cash controls. Every test makes its own cashier, manager and orders, so it
can be run again and again on a test database. Never run it against the
restaurant's live database: it takes real-looking sales.
"""
import uuid

import pytest
import requests

BASE = "http://localhost:8000/api/v1"
OWNER = {"email": "owner@greenbuffet.zm", "password": "greenbuffet2026"}


def api(method, path, token=None, key=False, **kwargs):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    if key:
        headers["Idempotency-Key"] = key if isinstance(key, str) else str(uuid.uuid4())
    return requests.request(method, BASE + path, headers=headers, timeout=15, **kwargs)


def login(email, password):
    r = api("POST", "/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def make_user(owner, role):
    email = f"{role}-{uuid.uuid4().hex[:6]}@test.zm"
    r = api("POST", "/admin/users", owner, json={"name": f"Test {role}", "email": email, "role_id": role})
    assert r.status_code in (200, 201), r.text
    temp = r.json()["temporary_password"]
    token = login(email, temp)
    new_password = "Test-" + uuid.uuid4().hex[:10]
    r = api("POST", "/auth/change-password", token, json={"current_password": temp, "new_password": new_password})
    assert r.status_code == 200, r.text
    return {"email": email, "password": new_password, "token": r.json()["token"], "id": r.json().get("id")}


@pytest.fixture(scope="module")
def owner():
    return login(**OWNER)


@pytest.fixture(scope="module")
def cashier(owner):
    c = make_user(owner, "cashier")
    r = api("POST", "/sales/shifts", c["token"], key=True, json={"float_ngwee": 50000})
    assert r.status_code == 201, r.text
    return c


@pytest.fixture(scope="module")
def manager(owner):
    return make_user(owner, "manager")


@pytest.fixture(scope="module")
def drink(owner):
    products = api("GET", "/menu/products", owner).json()
    p = next(p for p in products if p["is_active"] and p["price_ngwee"] == 5000 and not p["option_groups"])
    return p


def order(token, drink, qty=1, **extra):
    r = api("POST", "/sales/orders", token, key=True, json={
        "order_type": "takeaway", "lines": [{"product_id": drink["id"], "quantity": qty, "options": []}], **extra})
    return r


def pay(token, order_id, key=True, **body):
    return api("POST", f"/sales/orders/{order_id}/payments", token, key=key, json=body)


# ---- Phase 0 baseline -------------------------------------------------------

def test_cash_sale_gives_change(cashier, drink):
    o = order(cashier["token"], drink).json()
    r = pay(cashier["token"], o["id"], method="cash", amount_ngwee=5000, tendered_ngwee=10000)
    assert r.status_code == 200 and r.json()["status"] == "paid"
    assert r.json()["payments"][-1]["change_ngwee"] == 5000


def test_retried_payment_is_charged_once(cashier, drink):
    o = order(cashier["token"], drink).json()
    key = str(uuid.uuid4())
    a = pay(cashier["token"], o["id"], key=key, method="cash", amount_ngwee=5000)
    b = pay(cashier["token"], o["id"], key=key, method="cash", amount_ngwee=5000)
    assert a.json()["paid_ngwee"] == b.json()["paid_ngwee"] == 5000
    assert len(b.json()["payments"]) == 1


def test_split_payment_settles(cashier, drink):
    o = order(cashier["token"], drink, qty=2).json()
    pay(cashier["token"], o["id"], method="cash", amount_ngwee=4000)
    r = pay(cashier["token"], o["id"], method="airtel", amount_ngwee=6000,
            reference="T" + uuid.uuid4().hex[:8], confirmed=True)
    assert r.json()["status"] == "paid" and r.json()["outstanding_ngwee"] == 0


def test_books_balance(owner):
    tb = api("GET", "/books/trial-balance", owner).json()
    assert tb["balanced"] is True


# ---- Phase 1: mobile money --------------------------------------------------

def test_mobile_money_is_pending_until_confirmed(cashier, manager, drink):
    o = order(cashier["token"], drink).json()
    ref = "P" + uuid.uuid4().hex[:8]
    r = pay(cashier["token"], o["id"], method="mtn", amount_ngwee=5000, reference=ref)
    payment = r.json()["payments"][-1]
    assert payment["status"] == "pending"
    waiting = api("GET", "/sales/payments/unconfirmed", manager["token"]).json()
    assert any(w["reference"] == ref for w in waiting)
    done = api("POST", f"/sales/payments/{payment['id']}/confirm", manager["token"], json={"ok": True})
    assert done.json()["status"] == "confirmed"


def test_same_reference_cannot_pay_twice(cashier, drink):
    ref = "D" + uuid.uuid4().hex[:8]
    a = order(cashier["token"], drink).json()
    b = order(cashier["token"], drink).json()
    assert pay(cashier["token"], a["id"], method="airtel", amount_ngwee=5000, reference=ref).status_code == 200
    again = pay(cashier["token"], b["id"], method="airtel", amount_ngwee=5000, reference=ref)
    assert again.status_code == 409 and a["number"] in again.json()["detail"]


def test_failed_payment_stops_counting_and_books_still_balance(owner, cashier, manager, drink):
    o = order(cashier["token"], drink).json()
    r = pay(cashier["token"], o["id"], method="zamtel", amount_ngwee=5000, reference="F" + uuid.uuid4().hex[:8])
    pid = r.json()["payments"][-1]["id"]
    out = api("POST", f"/sales/payments/{pid}/confirm", manager["token"], json={"ok": False, "note": "not on statement"})
    assert out.json()["status"] == "failed" and out.json()["outstanding_ngwee"] == 5000
    assert api("GET", "/books/trial-balance", owner).json()["balanced"] is True


def test_cashier_cannot_confirm_payments(cashier):
    assert api("GET", "/sales/payments/unconfirmed", cashier["token"]).status_code == 403


# ---- Phase 1: discounts -----------------------------------------------------

def test_small_discount_needs_a_reason(cashier, drink):
    assert order(cashier["token"], drink, discount_ngwee=300).status_code == 422
    r = order(cashier["token"], drink, discount_ngwee=300, discount_reason="regular")
    assert r.status_code == 201 and r.json()["discount_ngwee"] == 300


def test_big_discount_needs_a_manager(cashier, manager, drink):
    refused = order(cashier["token"], drink, discount_ngwee=4900, discount_reason="friend")
    assert refused.status_code == 403
    wrong = order(cashier["token"], drink, discount_ngwee=4900, discount_reason="friend",
                  approval={"email": manager["email"], "password": "wrong-password"})
    assert wrong.status_code == 403
    ok = order(cashier["token"], drink, discount_ngwee=4900, discount_reason="spilt drink",
               approval={"email": manager["email"], "password": manager["password"]})
    assert ok.status_code == 201 and ok.json()["discount_approved_by"] == "Test manager"


def test_cashier_cannot_approve_own_discount(cashier, drink):
    r = order(cashier["token"], drink, discount_ngwee=4900, discount_reason="x",
              approval={"email": cashier["email"], "password": cashier["password"]})
    assert r.status_code == 403


# ---- Phase 1: refunds ------------------------------------------------------

def test_cashier_refund_needs_manager_approval(cashier, manager, drink):
    o = order(cashier["token"], drink).json()
    pay(cashier["token"], o["id"], method="cash", amount_ngwee=5000)
    alone = api("POST", f"/sales/orders/{o['id']}/refund", cashier["token"],
                json={"method": "cash", "amount_ngwee": 2000, "reason": "cold"})
    assert alone.status_code == 403
    ok = api("POST", f"/sales/orders/{o['id']}/refund", cashier["token"], json={
        "method": "cash", "amount_ngwee": 2000, "reason": "cold",
        "approval": {"email": manager["email"], "password": manager["password"]}})
    assert ok.status_code == 200 and ok.json()["paid_ngwee"] - 0 == 5000


# ---- Phase 1: changing and holding orders ---------------------------------

def test_unpaid_order_can_be_changed_paid_one_cannot(cashier, drink):
    o = order(cashier["token"], drink).json()
    body = {"order_type": "eat_in", "lines": [{"product_id": drink["id"], "quantity": 3, "options": []}]}
    changed = api("PUT", f"/sales/orders/{o['id']}", cashier["token"], json=body)
    assert changed.status_code == 200 and changed.json()["total_ngwee"] == 15000
    pay(cashier["token"], o["id"], method="cash", amount_ngwee=15000)
    assert api("PUT", f"/sales/orders/{o['id']}", cashier["token"], json=body).status_code == 409


# ---- Phase 1: cash and the blind count -------------------------------------

def test_open_till_is_blind_to_the_cashier(cashier, manager):
    mine = api("GET", "/sales/shifts/current", cashier["token"]).json()
    assert mine["cash_ngwee"] is None
    assert all(m["method"] != "cash" for m in mine["by_method"])


def test_cash_drop_counts_and_needs_another_person(cashier, manager):
    r = api("POST", "/sales/cash", cashier["token"], key=True,
            json={"kind": "drop", "amount_ngwee": 10000, "reason": "to the safe at lunch"})
    assert r.status_code == 201 and r.json()["status"] == "pending"
    own = api("POST", f"/sales/cash/{r.json()['id']}/decide", cashier["token"], json={"ok": True})
    assert own.status_code == 403
    ok = api("POST", f"/sales/cash/{r.json()['id']}/decide", manager["token"], json={"ok": True})
    assert ok.json()["status"] == "confirmed"


def test_short_till_needs_a_reason_then_a_review(owner, cashier, manager):
    shift = api("GET", "/sales/shifts/current", cashier["token"]).json()
    # Pay or cancel anything left open on this till first.
    for o in api("GET", "/sales/orders?status=open", owner).json():
        api("POST", f"/sales/orders/{o['id']}/cancel", owner, json={"reason": "test clean-up"})
    first = api("POST", f"/sales/shifts/{shift['id']}/close", cashier["token"], json={"counted_ngwee": 100})
    assert first.status_code == 409 and "short" in first.json()["detail"]
    closed = api("POST", f"/sales/shifts/{shift['id']}/close", cashier["token"],
                 json={"counted_ngwee": 100, "note": "gave too much change, I think"})
    assert closed.status_code == 200
    body = closed.json()
    assert body["first_count_ngwee"] == 100 and body["needs_review"] is True
    review = api("POST", f"/sales/shifts/{shift['id']}/review", manager["token"],
                 json={"note": "talked it through; watch change-giving"})
    assert review.json()["needs_review"] is False and review.json()["reviewed_by"] == "Test manager"
    assert api("GET", "/books/trial-balance", owner).json()["balanced"] is True


# ---- Phase 0/5: sessions and owners ----------------------------------------

def test_password_reset_ends_the_old_session(owner):
    u = make_user(owner, "cashier")
    assert api("GET", "/auth/me", u["token"]).status_code == 200
    users = api("GET", "/admin/users", owner).json()
    uid = next(x["id"] for x in users if x["email"] == u["email"])
    api("POST", f"/admin/users/{uid}/reset-password", owner)
    assert api("GET", "/auth/me", u["token"]).status_code == 401


def test_one_owner_cannot_switch_off_the_other(owner):
    second = make_user(owner, "owner")
    users = api("GET", "/admin/users", owner).json()
    first_id = next(x["id"] for x in users if x["email"] == OWNER["email"])
    r = api("PATCH", f"/admin/users/{first_id}", second["token"], json={"is_active": False})
    assert r.status_code == 409
    # By design no one can switch the test owner off through the system, so
    # the test tidies up directly in the (test) database.
    from sqlalchemy import update
    from app.core.database import SessionLocal
    from app.models.access import User
    with SessionLocal() as db:
        db.execute(update(User).where(User.email == second["email"]).values(is_active=False))
        db.commit()
