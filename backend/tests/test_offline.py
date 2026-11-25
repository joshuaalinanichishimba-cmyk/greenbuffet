"""Cash sales taken while the till could not reach the server, sent later.

    python -m pytest tests/test_offline.py

Runs against a test server and its test database, like the other suites.
Each test makes its own cashier and till.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from test_money_flows import OWNER, api, login, make_user

ago = lambda **kw: (datetime.now(timezone.utc) - timedelta(**kw)).isoformat()


@pytest.fixture(scope="module")
def owner():
    return login(**OWNER)


@pytest.fixture(scope="module")
def drink(owner):
    products = api("GET", "/menu/products", owner).json()
    return next(p for p in products if p["is_active"] and p["price_ngwee"] == 5000 and not p["option_groups"])


def cashier_with_till(owner):
    c = make_user(owner, "cashier")
    r = api("POST", "/sales/shifts", c["token"], key=True, json={"float_ngwee": 20000})
    assert r.status_code == 201, r.text
    ready = api("GET", "/sales/offline/ready", c["token"]).json()
    c["shift_id"] = ready["shift_id"]
    assert c["shift_id"]
    return c


def sale(c, drink, qty=1, charged=None, taken=None, sid=None, **extra):
    body = {
        "id": sid or str(uuid.uuid4()), "taken_at": taken or ago(minutes=2), "shift_id": c["shift_id"],
        "receipt_number": "T-1", "lines": [{"product_id": drink["id"], "quantity": qty}],
        "charged_ngwee": charged if charged is not None else drink["price_ngwee"] * qty,
        "tendered_ngwee": 10000, **extra,
    }
    return api("POST", "/sales/offline/sales", c["token"], json=body), body


def test_offline_sale_becomes_a_paid_order_with_kitchen_and_books(owner, drink):
    c = cashier_with_till(owner)
    r, body = sale(c, drink)
    assert r.status_code == 200, r.text
    out = r.json()
    o = out["order"]
    assert o["status"] == "paid" and o["total_ngwee"] == 5000 and o["outstanding_ngwee"] == 0
    assert o["payments"][0]["method"] == "cash" and o["change_ngwee"] == 5000
    assert out["already"] is False and out["notes"] == []
    assert "T-1" in o["note"]
    # the till's takings include it
    shift = api("GET", "/sales/shifts/current", c["token"]).json()
    assert shift["sales_ngwee"] == 5000
    # the kitchen has it, because it is recent
    board = api("GET", "/kitchen/tickets", owner)
    assert board.status_code == 200, board.text
    assert o["number"] in str(board.json())


def test_sending_the_same_sale_again_records_it_once(owner, drink):
    c = cashier_with_till(owner)
    sid = str(uuid.uuid4())
    first, _ = sale(c, drink, sid=sid)
    second, _ = sale(c, drink, sid=sid)
    third, _ = sale(c, drink, sid=sid.upper())
    assert first.status_code == second.status_code == third.status_code == 200
    assert first.json()["order"]["id"] == second.json()["order"]["id"] == third.json()["order"]["id"]
    assert second.json()["already"] is True
    shift = api("GET", "/sales/shifts/current", c["token"]).json()
    assert shift["sales_ngwee"] == 5000 and shift["orders"] == 1


def test_price_went_up_since_the_customer_paid(owner, drink):
    c = cashier_with_till(owner)
    r, _ = sale(c, drink, charged=4000)
    assert r.status_code == 200, r.text
    o = r.json()["order"]
    assert o["total_ngwee"] == 4000 and o["discount_ngwee"] == 1000 and o["outstanding_ngwee"] == 0
    assert "offline" in o["discount_reason"].lower()
    assert any("K10.00" in n for n in r.json()["notes"])


def test_price_went_down_since_the_customer_paid(owner, drink):
    c = cashier_with_till(owner)
    r, _ = sale(c, drink, charged=6000, tendered_ngwee=6000)
    assert r.status_code == 200, r.text
    o = r.json()["order"]
    assert o["total_ngwee"] == 5000 and o["outstanding_ngwee"] == 0
    assert any("K10.00 more" in n for n in r.json()["notes"])


def test_sold_out_or_hidden_since_does_not_undo_a_sale(owner, drink):
    c = cashier_with_till(owner)
    r = api("PATCH", f"/menu/products/{drink['id']}", owner, json={"is_available": False})
    assert r.status_code == 200, r.text
    try:
        normal = api("POST", "/sales/orders", c["token"], key=True,
                     json={"lines": [{"product_id": drink["id"], "quantity": 1}]})
        assert normal.status_code == 409 and "sold out" in normal.json()["detail"]
        offline, _ = sale(c, drink)
        assert offline.status_code == 200, offline.text
    finally:
        api("PATCH", f"/menu/products/{drink['id']}", owner, json={"is_available": True})


def test_a_sale_cannot_be_sent_onto_someone_elses_till(owner, drink):
    a = cashier_with_till(owner)
    b = cashier_with_till(owner)
    body = {"id": str(uuid.uuid4()), "taken_at": ago(minutes=1), "shift_id": a["shift_id"],
            "lines": [{"product_id": drink["id"], "quantity": 1}], "charged_ngwee": 5000}
    r = api("POST", "/sales/offline/sales", b["token"], json=body)
    assert r.status_code == 403


def test_dates_out_of_range_are_refused(owner, drink):
    c = cashier_with_till(owner)
    future, _ = sale(c, drink, taken=(datetime.now(timezone.utc) + timedelta(hours=2)).isoformat())
    old, _ = sale(c, drink, taken=ago(days=9))
    assert future.status_code == 422 and "future" in future.json()["detail"]
    assert old.status_code == 422 and "week" in old.json()["detail"]


def test_cash_given_cannot_be_less_than_charged(owner, drink):
    c = cashier_with_till(owner)
    r, _ = sale(c, drink, tendered_ngwee=1000)
    assert r.status_code == 422


def test_an_old_sale_is_kept_off_the_kitchen_board(owner, drink):
    c = cashier_with_till(owner)
    r, _ = sale(c, drink, taken=ago(hours=2))
    assert r.status_code == 200, r.text
    o = r.json()["order"]
    assert o["created_at"][:13] == o["paid_at"][:13]
    taken = datetime.fromisoformat(o["paid_at"])
    assert datetime.now(timezone.utc) - taken > timedelta(minutes=100)
    board = api("GET", "/kitchen/tickets", owner)
    assert board.status_code == 200, board.text
    assert o["number"] not in str(board.json())


def test_a_sale_arriving_after_the_till_closed_goes_on_that_till(owner, drink):
    c = cashier_with_till(owner)
    r = api("POST", f"/sales/shifts/{c['shift_id']}/close", c["token"], key=True,
            json={"counted_ngwee": 25000, "note": "offline sale in the drawer"})
    assert r.status_code == 200, r.text
    r, _ = sale(c, drink)
    assert r.status_code == 200, r.text
    assert any("closed" in n for n in r.json()["notes"])


def test_no_discounts_promos_or_card_methods_through_this_door(owner, drink):
    c = cashier_with_till(owner)
    r, _ = sale(c, drink, discount_ngwee=1000)
    # extra fields are ignored: the order is cash at the menu price
    assert r.status_code == 200
    o = r.json()["order"]
    assert o["discount_ngwee"] == 0 and o["payments"][0]["method"] == "cash"


def test_needs_the_till_permission(owner, drink):
    kitchen = make_user(owner, "kitchen")
    body = {"id": str(uuid.uuid4()), "taken_at": ago(minutes=1), "shift_id": "x",
            "lines": [{"product_id": drink["id"], "quantity": 1}], "charged_ngwee": 5000}
    assert api("POST", "/sales/offline/sales", kitchen["token"], json=body).status_code == 403
    assert api("POST", "/sales/offline/sales", None, json=body).status_code == 401
