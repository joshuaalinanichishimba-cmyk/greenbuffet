"""The IT workspace, emergency controls, security logging and the fix for
orders whose mobile money failed after hand-over.

    python -m pytest tests/test_it.py

Test server and TEST database only. The last test trips the sign-in rate
limit on purpose and then waits a minute for it to clear.
"""
import time
import uuid

import pytest
import requests
from sqlalchemy import select, text, update

from app.core.database import SessionLocal
from app.models.ops import RepairRun
from app.models.sales import Order
from app.services.ops import clean

BASE = "http://localhost:8000/api/v1"
OWNER = {"email": "owner@greenbuffet.zm", "password": "greenbuffet2026"}


def api(method, path, token=None, key=False, **kwargs):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    if key:
        headers["Idempotency-Key"] = str(uuid.uuid4())
    return requests.request(method, BASE + path, headers=headers, timeout=20, **kwargs)


def login(email, password):
    r = api("POST", "/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def make_user(owner, role):
    email = f"{role}-{uuid.uuid4().hex[:6]}@test.zm"
    r = api("POST", "/admin/users", owner, json={"name": f"Test {role} {uuid.uuid4().hex[:4]}", "email": email, "role_id": role})
    assert r.status_code in (200, 201), r.text
    temp = r.json()["temporary_password"]
    token = login(email, temp)
    password = "Test-" + uuid.uuid4().hex[:10]
    r = api("POST", "/auth/change-password", token, json={"current_password": temp, "new_password": password})
    return {"id": r.json().get("id") or "", "email": email, "password": password, "token": r.json()["token"]}


@pytest.fixture(scope="module")
def owner():
    return login(**OWNER)


@pytest.fixture(scope="module")
def it(owner):
    return make_user(owner, "it")


@pytest.fixture(scope="module")
def cashier(owner):
    c = make_user(owner, "cashier")
    api("POST", "/sales/shifts", c["token"], key=True, json={"float_ngwee": 50000})
    return c


@pytest.fixture(scope="module")
def drink(owner):
    products = api("GET", "/menu/products", owner).json()
    return next(p for p in products if p["is_active"] and p["price_ngwee"] == 5000 and not p["option_groups"])


def sell(token, drink):
    return api("POST", "/sales/orders", token, key=True, json={
        "order_type": "takeaway", "lines": [{"product_id": drink["id"], "quantity": 1, "options": []}]}).json()


# ---- the IT role sees the system, not the money --------------------------------

def test_it_sees_health_but_not_money_or_people(it):
    assert api("GET", "/it/overview", it["token"]).status_code == 200
    for path in ("/books/trial-balance", "/team", "/people/employees", "/reports/summary", "/payroll/runs"):
        assert api("GET", path, it["token"]).status_code in (403, 404), path
    assert api("POST", "/sales/orders", it["token"], key=True, json={"lines": []}).status_code in (403, 422)


def test_overview_never_claims_unchecked_things_are_fine(it):
    checks = {c["key"]: c for c in api("GET", "/it/overview", it["token"]).json()["checks"]}
    assert checks["database"]["status"] == "operational" and "ms" in checks["database"]["detail"]
    assert checks["email"]["status"] == "not_configured"
    assert checks["lenco"]["status"] == "not_configured"


def test_cashier_reports_a_problem_but_cannot_open_it(cashier, it):
    r = api("POST", "/tickets", cashier["token"], json={"description": "Printer prints blank receipts", "module": "till"})
    assert r.status_code == 201 and r.json()["number"].startswith("TKT")
    assert api("GET", "/it/overview", cashier["token"]).status_code == 403
    t = r.json()["id"]
    assert api("PATCH", f"/it/tickets/{t}", it["token"], json={"status": "resolved"}).status_code == 422
    done = api("PATCH", f"/it/tickets/{t}", it["token"], json={"status": "resolved", "resolution": "New paper roll, wrong side up"})
    assert done.json()["status"] == "resolved"
    mine = api("GET", "/tickets/mine", cashier["token"]).json()
    assert mine[0]["status"] == "resolved"


def test_incident_needs_a_resolution_to_close(it):
    i = api("POST", "/it/incidents", it["token"], json={"title": "Kitchen screen keeps disconnecting", "severity": "medium"}).json()
    assert api("PATCH", f"/it/incidents/{i['id']}", it["token"], json={"status": "resolved"}).status_code == 422
    ok = api("PATCH", f"/it/incidents/{i['id']}", it["token"], json={"status": "resolved", "resolution": "Router replaced", "note": "Monitored for a day"})
    assert ok.json()["status"] == "resolved" and ok.json()["notes"][0]["note"] == "Monitored for a day"


# ---- repairs are a fixed list -----------------------------------------------------

def test_unknown_or_bad_repairs_are_refused(it, owner):
    assert api("POST", "/it/repairs/drop_database/run", it["token"], json={"reason": "please"}).status_code == 404
    assert api("POST", "/it/repairs/close_expired_sessions/run", it["token"], json={"reason": "x"}).status_code == 422
    r = api("POST", "/it/repairs/revoke_account_sessions/run", it["token"],
            json={"reason": "lost phone test", "email": OWNER["email"]})
    assert r.status_code == 403   # owners are not signed out from IT
    assert api("GET", "/auth/me", owner).status_code == 200


def test_a_repair_cannot_run_twice_at_once(it):
    with SessionLocal() as db:
        from datetime import datetime, timezone
        db.add(RepairRun(operation="close_expired_sessions", risk="low", reason="t", status="running",
                         started_by="test", started_at=datetime.now(timezone.utc)))
        db.commit()
    r = api("POST", "/it/repairs/close_expired_sessions/run", it["token"], json={"reason": "second press"})
    assert r.status_code == 409
    with SessionLocal() as db:
        db.execute(update(RepairRun).where(RepairRun.started_by == "test").values(status="failed"))
        db.commit()


def test_repair_is_checked_afterwards(it):
    r = api("POST", "/it/repairs/close_expired_sessions/run", it["token"], json={"reason": "housekeeping"}).json()
    assert r["status"] == "succeeded" and r["verification"].startswith("Checked again")


# ---- emergency controls ------------------------------------------------------------

def test_cash_only_mode(it, cashier, drink):
    assert api("POST", "/it/controls/electronic_payments", it["token"],
               json={"enabled": False, "reason": "Network down", "password": "wrong"}).status_code == 403
    assert api("POST", "/it/controls/electronic_payments", it["token"],
               json={"enabled": False, "reason": "Network down", "password": it["password"]}).status_code == 200
    try:
        o = sell(cashier["token"], drink)
        r = api("POST", f"/sales/orders/{o['id']}/payments", cashier["token"], key=True,
                json={"method": "mtn", "amount_ngwee": 5000, "reference": "X" + uuid.uuid4().hex[:8]})
        assert r.status_code == 409 and "cash only" in r.json()["detail"]
        r = api("POST", f"/sales/orders/{o['id']}/payments", cashier["token"], key=True,
                json={"method": "cash", "amount_ngwee": 5000})
        assert r.status_code == 200
    finally:
        api("POST", "/it/controls/electronic_payments", it["token"],
            json={"enabled": True, "reason": "Network back", "password": it["password"]})


def test_read_only_mode_stops_changes_but_not_looking(it, cashier, owner, drink):
    api("POST", "/it/controls/read_only", it["token"], json={"enabled": True, "reason": "Fixing the books", "password": it["password"]})
    try:
        r = api("POST", "/sales/orders", cashier["token"], key=True, json={
            "order_type": "takeaway", "lines": [{"product_id": drink["id"], "quantity": 1, "options": []}]})
        assert r.status_code == 503
        assert api("GET", "/sales/orders", cashier["token"]).status_code == 200
        assert api("POST", "/tickets", cashier["token"], json={"description": "Cannot sell, is it down?"}).status_code == 201
    finally:
        api("POST", "/it/controls/read_only", it["token"], json={"enabled": False, "reason": "Fixed", "password": it["password"]})
    assert sell(cashier["token"], drink)["number"]


def test_stopping_orders(it, cashier, drink):
    api("POST", "/it/controls/take_orders", it["token"], json={"enabled": False, "reason": "Gas ran out", "password": it["password"]})
    try:
        r = api("POST", "/sales/orders", cashier["token"], key=True, json={
            "order_type": "takeaway", "lines": [{"product_id": drink["id"], "quantity": 1, "options": []}]})
        assert r.status_code == 503 and "stopped" in r.json()["detail"]
    finally:
        api("POST", "/it/controls/take_orders", it["token"], json={"enabled": True, "reason": "Gas delivered", "password": it["password"]})


# ---- audit and errors -----------------------------------------------------------------

def test_audit_log_cannot_be_edited_or_deleted():
    with SessionLocal() as db:
        for sql in ("UPDATE audit_log SET detail = 'x' WHERE id = (SELECT id FROM audit_log LIMIT 1)",
                    "DELETE FROM audit_log WHERE id = (SELECT id FROM audit_log LIMIT 1)"):
            with pytest.raises(Exception):
                db.execute(text(sql))
                db.commit()
            db.rollback()


def test_error_messages_are_cleaned_of_secrets():
    cleaned = clean("connect failed postgresql+psycopg://gb:Sup3rSecret@db/x password=hunter2 token: abc.def")
    assert "Sup3rSecret" not in cleaned and "hunter2" not in cleaned and "abc.def" not in cleaned


def test_refused_access_is_logged(cashier, owner):
    api("GET", "/books/trial-balance", cashier["token"])
    events = api("GET", "/it/security", owner).json()
    assert any(e["kind"] == "access_refused" and e["account"] == cashier["email"] for e in events)


# ---- failed mobile money after hand-over -------------------------------------------------

def test_failed_payment_order_owes_again_and_is_paid_once(owner, cashier, drink):
    o = sell(cashier["token"], drink)
    r = api("POST", f"/sales/orders/{o['id']}/payments", cashier["token"], key=True,
            json={"method": "airtel", "amount_ngwee": 5000, "reference": "F" + uuid.uuid4().hex[:8]})
    pid = r.json()["payments"][-1]["id"]
    api("POST", f"/sales/payments/{pid}/confirm", owner, json={"ok": False, "note": "not on statement"})
    order = api("GET", f"/sales/orders/{o['id']}", owner).json()
    assert order["status"] == "open" and order["outstanding_ngwee"] == 5000
    # It cannot be cancelled away: the food was handed over.
    assert api("POST", f"/sales/orders/{o['id']}/cancel", owner, json={"reason": "customer left"}).status_code == 409
    with SessionLocal() as db:
        moves_before = db.scalar(text("SELECT count(*) FROM stock_moves WHERE reference = :n"), {"n": o["number"]})
        tickets_before = db.scalar(text("SELECT count(*) FROM kitchen_items WHERE order_id = :i"), {"i": o["id"]})
    paid = api("POST", f"/sales/orders/{o['id']}/payments", cashier["token"], key=True,
               json={"method": "cash", "amount_ngwee": 5000})
    assert paid.json()["status"] == "paid"
    with SessionLocal() as db:
        assert db.scalar(text("SELECT count(*) FROM stock_moves WHERE reference = :n"), {"n": o["number"]}) == moves_before
        assert db.scalar(text("SELECT count(*) FROM kitchen_items WHERE order_id = :i"), {"i": o["id"]}) == tickets_before
        assert db.scalar(text("SELECT count(*) FROM journal_entries WHERE source = 'sale' AND reference = :n"),
                         {"n": o["number"]}) == 1
    assert api("GET", "/books/trial-balance", owner).json()["balanced"] is True


def test_reopen_repair_fixes_old_owing_orders(owner, it, cashier, drink):
    o = sell(cashier["token"], drink)
    r = api("POST", f"/sales/orders/{o['id']}/payments", cashier["token"], key=True,
            json={"method": "zamtel", "amount_ngwee": 5000, "reference": "Z" + uuid.uuid4().hex[:8]})
    pid = r.json()["payments"][-1]["id"]
    api("POST", f"/sales/payments/{pid}/confirm", owner, json={"ok": False})
    # As it was before this fix: marked paid although it owes.
    with SessionLocal() as db:
        db.execute(update(Order).where(Order.id == o["id"]).values(status="paid"))
        db.commit()
    preview = api("POST", "/it/repairs/reopen_orders_owing/preview", it["token"]).json()
    assert any(i["ref"] == o["number"] for i in preview["items"])
    run = api("POST", "/it/repairs/reopen_orders_owing/run", it["token"], json={"reason": "orders owing after failed mobile money"}).json()
    assert run["status"] == "succeeded" and run["verification"] == "Checked again: none left."
    assert api("GET", f"/sales/orders/{o['id']}", owner).json()["status"] == "open"


# ---- last: the rate limit (waits a minute afterwards) -------------------------------------

def test_sign_in_is_rate_limited():
    import os
    limit = int(os.environ.get("LOGIN_RATE_PER_MINUTE", "30"))
    codes = [api("POST", "/auth/login", json={"email": f"nobody-{i}@test.zm", "password": "x"}).status_code
             for i in range(limit + 5)]
    assert 429 in codes
    time.sleep(61)
