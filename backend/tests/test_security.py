"""Security tests.

These are the checks that must keep passing. Each one stands for something
that would be a real problem in a restaurant: someone reading the payroll,
a till charging twice, a disabled employee still signing in.

Run them with the backend running:

    cd backend
    .\\.venv\\Scripts\\python.exe -m pytest tests -q
"""
import base64
import json
import os
import uuid

import pytest
import requests

BASE = os.getenv("GREENBUFFET_TEST_API_URL", "http://localhost:8000/api/v1")
OWNER = {"email": "owner@greenbuffet.zm", "password": os.getenv("GREENBUFFET_TEST_PASSWORD", "")}
TIMEOUT = 20


def api(method, path, token=None, **kwargs):
    headers = kwargs.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return requests.request(method, BASE + path, headers=headers, timeout=TIMEOUT, **kwargs)


@pytest.fixture(scope="session")
def owner():
    if not OWNER["password"]:
        pytest.skip("Set GREENBUFFET_TEST_PASSWORD to the disposable test owner password.")
    response = api("POST", "/auth/login", json=OWNER)
    if response.status_code != 200:
        pytest.skip("The disposable test owner credentials were rejected.")
    return response.json()["token"]


@pytest.fixture(scope="session")
def cashier(owner):
    """A cashier account, made or reset so the tests always have one."""
    email = "test-cashier@greenbuffet.zm"
    made = api("POST", "/admin/users", owner,
               json={"name": "Test Cashier", "email": email, "role_id": "cashier"})
    if made.status_code == 201:
        password = made.json()["temporary_password"]
    else:
        users = api("GET", "/admin/users", owner).json()
        found = next(u for u in users if u["email"] == email)
        password = api("POST", f"/admin/users/{found['id']}/reset-password", owner).json()["temporary_password"]
    token = api("POST", "/auth/login", json={"email": email, "password": password}).json()["token"]
    return token


# ---------------------------------------------------------------------------
# who can get in
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", [
    "/admin/users", "/books/trial-balance", "/people/payroll/runs",
    "/sales/orders", "/stock/levels", "/reports/dashboard", "/settings",
])
def test_no_token_is_refused(path):
    assert api("GET", path).status_code in (401, 403)


def test_wrong_password_is_refused():
    assert api("POST", "/auth/login", json={**OWNER, "password": "not it"}).status_code in (401, 429)


@pytest.mark.parametrize("attempt", ["' OR 1=1 --", "x'; DROP TABLE users; --", "%' --"])
def test_sql_in_the_login_box_does_nothing(attempt):
    assert api("POST", "/auth/login", json={"email": attempt, "password": "x"}).status_code in (401, 429)


def test_a_tampered_token_is_refused(owner):
    head, body, signature = owner.split(".")

    def encode(data):
        return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")

    def decode(part):
        return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))

    claims = decode(body)
    claims["sub"] = "somebody-else"
    assert api("GET", "/auth/me", f"{head}.{encode(claims)}.{signature}").status_code == 401

    header = decode(head)
    header["alg"] = "none"
    assert api("GET", "/auth/me", f"{encode(header)}.{body}.").status_code == 401
    assert api("GET", "/auth/me", f"{head}.{body}.AAAA").status_code == 401


def test_a_disabled_account_cannot_use_its_token(owner, cashier):
    me = api("GET", "/auth/me", cashier).json()["user"]
    assert api("GET", "/sales/orders", cashier).status_code == 200
    api("PATCH", f"/admin/users/{me['id']}", owner, json={"is_active": False})
    try:
        assert api("GET", "/sales/orders", cashier).status_code == 403
    finally:
        api("PATCH", f"/admin/users/{me['id']}", owner, json={"is_active": True})


# ---------------------------------------------------------------------------
# what a cashier may not do
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("method,path", [
    ("GET", "/admin/users"),
    ("GET", "/admin/audit"),
    ("GET", "/books/trial-balance"),
    ("GET", "/books/journal"),
    ("GET", "/people/employees"),
    ("GET", "/people/payroll/runs"),
    ("GET", "/reports/dashboard"),
    ("GET", "/stock/levels"),
    ("POST", "/settings/backups"),
])
def test_a_cashier_is_kept_out(cashier, method, path):
    assert api(method, path, cashier, json={}).status_code == 403


def test_a_cashier_cannot_change_prices(owner, cashier):
    product = api("GET", "/menu/products", owner).json()[0]
    assert api("PATCH", f"/menu/products/{product['id']}", cashier,
               json={"price_ngwee": 1}).status_code == 403


def test_a_cashier_cannot_promote_themselves(owner, cashier):
    me = api("GET", "/auth/me", cashier).json()["user"]
    assert api("PATCH", f"/admin/users/{me['id']}", cashier, json={"role_id": "owner"}).status_code == 403


def test_a_cashier_sees_dish_photographs_but_not_the_paperwork(cashier):
    """The till needs the dishes; a supplier contract is none of its business."""
    for document in api("GET", "/settings/files", cashier).json():
        assert document["attached_to"] == "product" and document["kind"] == "photo"


# ---------------------------------------------------------------------------
# money
# ---------------------------------------------------------------------------

def test_the_same_order_sent_twice_is_one_order(owner):
    shift = api("GET", "/sales/shifts/current", owner).json()
    if not shift or not shift["is_open"]:
        api("POST", "/sales/shifts", owner, json={"float_ngwee": 20000})
    product = next(p for p in api("GET", "/menu/products", owner).json() if not p["option_groups"])
    key = str(uuid.uuid4())
    body = {"lines": [{"product_id": product["id"], "quantity": 1}]}
    first = api("POST", "/sales/orders", owner, json=body, headers={"Idempotency-Key": key})
    second = api("POST", "/sales/orders", owner, json=body, headers={"Idempotency-Key": key})
    assert first.json()["id"] == second.json()["id"]
    api("POST", f"/sales/orders/{first.json()['id']}/cancel", owner, json={"reason": "test run"})


def test_an_unbalanced_journal_entry_is_refused(owner):
    response = api("POST", "/books/journal", owner, json={
        "memo": "Does not balance",
        "lines": [{"account_code": "6100", "debit_ngwee": 100},
                  {"account_code": "1010", "credit_ngwee": 90}],
    })
    assert response.status_code == 422


def test_nobody_approves_their_own_journal_entry(owner):
    written = api("POST", "/books/journal", owner, json={
        "memo": "Written to test approval",
        "lines": [{"account_code": "6900", "debit_ngwee": 100},
                  {"account_code": "1000", "credit_ngwee": 100}],
    }).json()
    assert api("POST", f"/books/journal/{written['id']}/approve", owner).status_code == 409


def test_the_books_balance(owner):
    trial = api("GET", "/books/trial-balance", owner).json()
    assert trial["balanced"], f"out by {trial['total_debit_ngwee'] - trial['total_credit_ngwee']} ngwee"
    sheet = api("GET", "/books/balance-sheet", owner).json()
    assert sheet["balanced"], f"out by {sheet['difference_ngwee']} ngwee"


# ---------------------------------------------------------------------------
# files
# ---------------------------------------------------------------------------

def test_a_file_that_is_not_an_image_or_pdf_is_refused(owner):
    response = api("POST", "/settings/files", owner,
                   files={"file": ("notes.txt", b"hello", "text/plain")},
                   data={"kind": "other", "attached_to": "business"})
    assert response.status_code == 422


def test_an_oversized_file_is_refused(owner):
    response = api("POST", "/settings/files", owner,
                   files={"file": ("big.jpg", b"x" * (9 * 1024 * 1024), "image/jpeg")},
                   data={"kind": "photo", "attached_to": "business"})
    assert response.status_code == 413


def test_security_headers_are_present():
    headers = requests.get(BASE + "/health", timeout=TIMEOUT).headers
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
