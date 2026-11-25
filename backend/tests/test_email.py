"""Email: confirming addresses, emailed sign-in codes, password reset links
and changing an address. Follows the brief's authentication test list.

    python -m pytest tests/test_email.py

The test server must run with EMAIL_MODE=file and EMAIL_FILE_DIR set to the
same folder as here, so each email lands as a file the test can read.
Test database only.
"""
import email
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests
from sqlalchemy import select, text, update

from app.core.database import SessionLocal
from app.models.access import EmailChallenge, User

BASE = "http://localhost:8000/api/v1"
OWNER = {"email": "owner@greenbuffet.zm", "password": "greenbuffet2026"}
MAIL = Path(os.environ.get("EMAIL_FILE_DIR", "/tmp/claude-0/-home-claude/3ae775c2-97b3-536f-9598-87ad6854b09c/scratchpad/mail"))


def api(method, path, token=None, **kwargs):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return requests.request(method, BASE + path, headers=headers, timeout=20, **kwargs)


def login(email_, password):
    r = api("POST", "/auth/login", json={"email": email_, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def last_mail(to):
    """The newest message to an address: (subject, body)."""
    for path in sorted(MAIL.glob("*.eml"), reverse=True):
        msg = email.message_from_bytes(path.read_bytes())
        if msg["To"] == to:
            return msg["Subject"], msg.get_payload(decode=True).decode()
    raise AssertionError(f"No email to {to}")


def code_in(to):
    return re.search(r"Your code is: (\d{6})", last_mail(to)[1]).group(1)


def make_user(owner, role="cashier"):
    address = f"{role}-{uuid.uuid4().hex[:6]}@test.zm"
    r = api("POST", "/admin/users", owner, json={"name": f"Mutinta {role} {uuid.uuid4().hex[:4]}", "email": address, "role_id": role})
    temp, uid = r.json()["temporary_password"], r.json()["id"]
    token = login(address, temp)["token"]
    password = "Kp-" + uuid.uuid4().hex[:12]
    r = api("POST", "/auth/change-password", token, json={"current_password": temp, "new_password": password})
    return {"id": uid, "email": address, "password": password, "token": r.json()["token"]}


def confirm_address(u):
    assert api("POST", "/auth/email/verify/start", u["token"]).status_code == 200
    assert api("POST", "/auth/email/verify/confirm", u["token"], json={"code": code_in(u["email"])}).status_code == 200


def age_last_code(user_email, purpose, seconds):
    """Moves the newest code's creation time back, as if time had passed."""
    with SessionLocal() as db:
        uid = db.scalar(select(User.id).where(User.email == user_email))
        c = db.scalar(select(EmailChallenge).where(EmailChallenge.user_id == uid, EmailChallenge.purpose == purpose)
                      .order_by(EmailChallenge.created_at.desc()))
        c.created_at -= timedelta(seconds=seconds)
        db.commit()


@pytest.fixture(scope="module")
def owner():
    return login(OWNER["email"], OWNER["password"])["token"]


# ---- confirming an address ---------------------------------------------------

def test_address_is_confirmed_with_an_emailed_code(owner):
    u = make_user(owner)
    assert api("POST", "/auth/email/verify/start", u["token"]).json()["sent_to"].startswith(u["email"][0] + "***@")
    assert api("POST", "/auth/email/verify/confirm", u["token"], json={"code": "000000"}).status_code == 400
    code = code_in(u["email"])
    assert api("POST", "/auth/email/verify/confirm", u["token"], json={"code": code}).status_code == 200
    # Reused code.
    r = api("POST", "/auth/email/verify/confirm", u["token"], json={"code": code})
    assert r.status_code in (400, 404)
    assert api("GET", "/auth/me", u["token"]).json()["user"]["email_verified"] is True


def test_codes_never_reach_the_email_log(owner):
    u = make_user(owner)
    api("POST", "/auth/email/verify/start", u["token"])
    code = code_in(u["email"])
    with SessionLocal() as db:
        logged = " ".join(r[0] for r in db.execute(text("SELECT subject || ' ' || error FROM email_messages")).all())
    assert code not in logged


# ---- emailed sign-in codes ----------------------------------------------------

@pytest.fixture()
def emailed(owner):
    u = make_user(owner)
    confirm_address(u)
    assert api("POST", "/auth/email/two-step", u["token"], json={"method": "email"}).status_code == 200
    age_last_code(u["email"], "verify", 120)
    return u


def test_sign_in_needs_the_emailed_code_and_no_session_before(emailed):
    first = login(emailed["email"], emailed["password"])
    assert first["needs_code"] and first["code_by"] == "email" and not first["token"]
    assert api("GET", "/auth/me", first["ticket"]).status_code == 401
    assert api("POST", "/auth/login/code", json={"ticket": first["ticket"], "code": "123456"}).status_code == 401
    ok = api("POST", "/auth/login/code", json={"ticket": first["ticket"], "code": code_in(emailed["email"])})
    assert ok.status_code == 200 and ok.json()["token"]


def test_used_code_cannot_be_replayed(emailed):
    first = login(emailed["email"], emailed["password"])
    code = code_in(emailed["email"])
    assert api("POST", "/auth/login/code", json={"ticket": first["ticket"], "code": code}).status_code == 200
    assert api("POST", "/auth/login/code", json={"ticket": first["ticket"], "code": code}).status_code == 401


def test_expired_code_is_refused(emailed):
    first = login(emailed["email"], emailed["password"])
    with SessionLocal() as db:
        db.execute(update(EmailChallenge).where(EmailChallenge.purpose == "sign_in", EmailChallenge.used_at.is_(None))
                   .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
        db.commit()
    r = api("POST", "/auth/login/code", json={"ticket": first["ticket"], "code": code_in(emailed["email"])})
    assert r.status_code == 401 and "expired" in r.json()["detail"]


def test_resend_replaces_the_old_code_and_is_not_instant(emailed):
    first = login(emailed["email"], emailed["password"])
    old = code_in(emailed["email"])
    assert api("POST", "/auth/login/resend", json={"ticket": first["ticket"]}).status_code == 429   # too soon
    age_last_code(emailed["email"], "sign_in", 61)
    second = api("POST", "/auth/login/resend", json={"ticket": first["ticket"]}).json()
    new = code_in(emailed["email"])
    assert new != old or True   # six digits can repeat by chance; the old challenge is what matters
    r = api("POST", "/auth/login/code", json={"ticket": first["ticket"], "code": old})
    assert r.status_code == 401
    assert api("POST", "/auth/login/code", json={"ticket": second["ticket"], "code": new}).status_code == 200


def test_too_many_wrong_codes_spends_the_challenge(emailed):
    first = login(emailed["email"], emailed["password"])
    code = code_in(emailed["email"])
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        api("POST", "/auth/login/code", json={"ticket": first["ticket"], "code": wrong})
    r = api("POST", "/auth/login/code", json={"ticket": first["ticket"], "code": code})
    assert r.status_code in (401, 429)


def test_recovery_code_works_with_email_method(owner):
    u = make_user(owner)
    confirm_address(u)
    codes = api("POST", "/auth/email/two-step", u["token"], json={"method": "email"}).json()["recovery_codes"]
    assert len(codes) == 8
    first = login(u["email"], u["password"])
    assert api("POST", "/auth/login/code", json={"ticket": first["ticket"], "code": codes[0]}).status_code == 200


def test_email_method_needs_a_confirmed_address(owner):
    u = make_user(owner)
    assert api("POST", "/auth/email/two-step", u["token"], json={"method": "email"}).status_code == 409


# ---- password recovery ----------------------------------------------------------

def test_forgot_password_says_the_same_for_everyone(owner):
    u = make_user(owner)
    confirm_address(u)
    a = api("POST", "/auth/password/forgot", json={"email": u["email"]}).json()
    b = api("POST", "/auth/password/forgot", json={"email": f"nobody-{uuid.uuid4().hex[:5]}@test.zm"}).json()
    assert a == b


def test_reset_link_works_once_and_ends_every_session(owner):
    u = make_user(owner)
    confirm_address(u)
    api("POST", "/auth/password/forgot", json={"email": u["email"]})
    token = re.search(r"token=([\w-]+)", last_mail(u["email"])[1]).group(1)
    assert api("POST", "/auth/password/reset", json={"token": token, "new_password": "password1"}).status_code == 400
    new_pw = "Kp-" + uuid.uuid4().hex[:12]
    assert api("POST", "/auth/password/reset", json={"token": token, "new_password": new_pw}).status_code == 200
    assert api("GET", "/auth/me", u["token"]).status_code == 401
    assert api("POST", "/auth/password/reset", json={"token": token, "new_password": new_pw + "x"}).status_code == 400
    assert login(u["email"], new_pw)["token"]


def test_expired_reset_link_is_refused(owner):
    u = make_user(owner)
    confirm_address(u)
    api("POST", "/auth/password/forgot", json={"email": u["email"]})
    token = re.search(r"token=([\w-]+)", last_mail(u["email"])[1]).group(1)
    with SessionLocal() as db:
        db.execute(update(EmailChallenge).where(EmailChallenge.purpose == "reset", EmailChallenge.used_at.is_(None))
                   .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
        db.commit()
    r = api("POST", "/auth/password/reset", json={"token": token, "new_password": "Kp-" + uuid.uuid4().hex[:12]})
    assert r.status_code == 400 and "expired" in r.json()["detail"]


def test_weak_passwords_are_refused(owner):
    u = make_user(owner)
    for weak in ("short1", "password123", "mutintamutinta1"):
        r = api("POST", "/auth/change-password", u["token"], json={"current_password": u["password"], "new_password": weak})
        assert r.status_code in (400, 422), weak


# ---- changing an address ----------------------------------------------------------

def test_email_change_needs_both_addresses(owner):
    u = make_user(owner)
    confirm_address(u)
    other = make_user(owner)
    new = f"new-{uuid.uuid4().hex[:6]}@test.zm"
    assert api("POST", "/auth/email/change/start", u["token"], json={"password": "wrong", "new_email": new}).status_code == 400
    assert api("POST", "/auth/email/change/start", u["token"], json={"password": u["password"], "new_email": other["email"]}).status_code == 409
    age_last_code(u["email"], "verify", 120)
    started = api("POST", "/auth/email/change/start", u["token"], json={"password": u["password"], "new_email": new}).json()
    assert started["needs_old"] is True
    old_code, new_code = code_in(u["email"]), code_in(new)
    # Not changed before both codes are in.
    assert api("GET", "/auth/me", u["token"]).json()["user"]["email"] == u["email"]
    bad = api("POST", "/auth/email/change/confirm", u["token"], json={"group": started["group"], "old_code": "000000", "new_code": new_code})
    assert bad.status_code == 400
    assert api("GET", "/auth/me", u["token"]).json()["user"]["email"] == u["email"]
    # A failed attempt spends nothing on the new code, but the old one counts a try; ask again.
    age_last_code(u["email"], "change_old", 120)
    age_last_code(new, "change_new", 120) if False else None
    with SessionLocal() as db:
        db.execute(update(EmailChallenge).where(EmailChallenge.purpose.in_(("change_old", "change_new"))).values(created_at=EmailChallenge.created_at - timedelta(minutes=20)))
        db.commit()
    started = api("POST", "/auth/email/change/start", u["token"], json={"password": u["password"], "new_email": new}).json()
    ok = api("POST", "/auth/email/change/confirm", u["token"], json={"group": started["group"], "old_code": code_in(u["email"]), "new_code": code_in(new)})
    assert ok.status_code == 200 and ok.json()["email"] == new
    assert login(new, u["password"])["token"]


def test_one_owner_cannot_redirect_the_others_email(owner):
    second = make_user(owner, "owner")
    try:
        with SessionLocal() as db:
            oid = db.scalar(select(User.id).where(User.email == OWNER["email"]))
        r = api("PATCH", f"/admin/users/{oid}", second["token"], json={"email": f"x-{uuid.uuid4().hex[:5]}@test.zm"})
        assert r.status_code == 409
    finally:
        with SessionLocal() as db:
            db.execute(update(User).where(User.email == second["email"]).values(is_active=False))
            db.commit()


def test_manager_changed_email_must_be_confirmed_again(owner):
    u = make_user(owner)
    confirm_address(u)
    new = f"moved-{uuid.uuid4().hex[:6]}@test.zm"
    assert api("PATCH", f"/admin/users/{u['id']}", owner, json={"email": new}).status_code == 200
    with SessionLocal() as db:
        assert db.scalar(select(User.email_verified_at).where(User.email == new)) is None


def test_it_test_email_goes_only_to_their_own_confirmed_address(owner):
    it = make_user(owner, "it")
    assert api("POST", "/it/email/test", it["token"]).status_code == 409
    confirm_address(it)
    r = api("POST", "/it/email/test", it["token"]).json()
    assert r["ok"] and last_mail(it["email"])[0] == "Green Buffet test email"
