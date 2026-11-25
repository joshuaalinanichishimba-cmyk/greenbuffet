"""Profiles, presence, sessions, the lock screen and two-step sign-in.

    python -m pytest tests/test_profiles.py

Against a running test server and a TEST database only: it makes accounts,
suspends and archives them, and moves session times about to stand in for
time passing. Never against the restaurant's live database.

Each test follows one line of the brief's "Mandatory testing" list.
"""
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from sqlalchemy import select, update

from app.core.database import SessionLocal
from app.models.access import AuditLog, Setting, User, UserSession
from app.services import twostep

BASE = "http://localhost:8000/api/v1"
OWNER = {"email": "owner@greenbuffet.zm", "password": "greenbuffet2026"}


def api(method, path, token=None, **kwargs):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    headers.update(kwargs.pop("headers", {}))
    return requests.request(method, BASE + path, headers=headers, timeout=15, **kwargs)


def login(email, password, ua=None):
    r = api("POST", "/auth/login", json={"email": email, "password": password},
            headers={"User-Agent": ua} if ua else {})
    assert r.status_code == 200, r.text
    return r.json()


def make_user(owner, role, name=None):
    email = f"{role}-{uuid.uuid4().hex[:6]}@test.zm"
    r = api("POST", "/admin/users", owner, json={"name": name or f"Test {role} {uuid.uuid4().hex[:4]}",
                                                  "email": email, "role_id": role})
    assert r.status_code in (200, 201), r.text
    body = r.json()
    temp = body["temporary_password"]
    token = login(email, temp)["token"]
    password = "Test-" + uuid.uuid4().hex[:10]
    r = api("POST", "/auth/change-password", token, json={"current_password": temp, "new_password": password})
    assert r.status_code == 200, r.text
    return {"id": body["id"], "email": email, "password": password, "token": r.json()["token"], "name": body["name"]}


def switch_off(user_id):
    """Tidy up an owner made by a test: no one can do that through the system."""
    with SessionLocal() as db:
        db.execute(update(User).where(User.id == user_id).values(is_active=False, archived_at=datetime.now(timezone.utc)))
        db.commit()


def age_session(token_session_id, **fields):
    with SessionLocal() as db:
        db.execute(update(UserSession).where(UserSession.id == token_session_id).values(**fields))
        db.commit()


def sid_of(token):
    return api("GET", "/auth/me", token).json()["session_id"]


@pytest.fixture(scope="module")
def owner():
    return login(**OWNER)["token"]


# ---- 1. both owners have independent profiles --------------------------------

def test_both_owners_have_their_own_profiles(owner):
    second = make_user(owner, "owner")
    try:
        mine = api("GET", "/profile/me", owner).json()
        theirs = api("GET", "/profile/me", second["token"]).json()
        assert mine["id"] != theirs["id"] and mine["role_id"] == theirs["role_id"] == "owner"
        # Each sees the other's profile, with the same powers over staff.
        seen = api("GET", f"/team/{mine['id']}", second["token"]).json()
        assert seen["name"] == mine["name"] and "logins" in seen["tabs"]
        # And neither can suspend or archive the other.
        r = api("POST", f"/team/{mine['id']}/suspend", second["token"], json={"reason": "test"})
        assert r.status_code == 409
        r = api("POST", f"/team/{mine['id']}/archive", second["token"], json={"reason": "test"})
        assert r.status_code == 409
    finally:
        switch_off(second["id"])


# ---- 2. several cashiers and kitchen staff, each their own ---------------------

def test_each_cashier_and_cook_has_a_profile(owner):
    people = [make_user(owner, "cashier"), make_user(owner, "cashier"), make_user(owner, "kitchen")]
    listed = {p["id"]: p for p in api("GET", "/team", owner).json()}
    for person in people:
        assert person["id"] in listed
        me = api("GET", "/profile/me", person["token"]).json()
        assert me["id"] == person["id"] and me["is_me"] is True
        assert "payroll" in me["tabs"] and "security" in me["tabs"]


# ---- 3-5. presence follows the heartbeat, not the session ------------------------

def test_presence_follows_real_connection(owner):
    c = make_user(owner, "cashier")
    sid = sid_of(c["token"])
    status = lambda: api("GET", f"/team/{c['id']}", owner).json()["presence"]["status"]  # noqa: E731
    assert api("POST", "/presence/heartbeat", c["token"], json={"active": True}).status_code == 200
    assert status() == "online"

    # Connected, but nobody has touched it for longer than the away time.
    age_session(sid, last_active_at=datetime.now(timezone.utc) - timedelta(minutes=30))
    api("POST", "/presence/heartbeat", c["token"], json={"active": False})
    assert status() == "away"

    # The heartbeat stopped five minutes ago: a dropped network or load shedding.
    age_session(sid, last_seen_at=datetime.now(timezone.utc) - timedelta(minutes=5))
    assert status() == "lost"

    # Power back: the next heartbeat brings it straight back.
    api("POST", "/presence/heartbeat", c["token"], json={"active": True})
    assert status() == "online"

    # Silent for more than half an hour: offline.
    age_session(sid, last_seen_at=datetime.now(timezone.utc) - timedelta(minutes=45))
    assert status() == "offline"

    # A session that has never sent a heartbeat is not shown as online.
    age_session(sid, last_seen_at=None, last_active_at=None)
    assert status() == "unknown"

    # Closing the page says so; signing out ends it.
    api("POST", "/presence/heartbeat", c["token"], json={"active": True})
    api("POST", "/presence/heartbeat", c["token"], json={"closing": True})
    assert status() == "offline"
    api("POST", "/presence/heartbeat", c["token"], json={"active": True})
    assert api("POST", "/auth/logout", c["token"], json={}).status_code == 200
    assert status() == "offline"
    assert api("GET", "/auth/me", c["token"]).status_code == 401


# ---- 6. attendance is separate from being online -----------------------------------

def test_on_duty_comes_from_clocking_not_from_being_online(owner):
    c = make_user(owner, "cashier")
    r = api("POST", "/people/employees", owner, json={"name": c["name"], "basic_ngwee": 300000, "user_id": c["id"],
                                                        "job_title": "Cashier", "department": "Counter"})
    assert r.status_code == 201, r.text
    assert api("POST", "/people/clock-in", c["token"], json={}).status_code == 200
    api("POST", "/auth/logout", c["token"], json={})
    seen = api("GET", f"/team/{c['id']}", owner).json()
    assert seen["presence"]["status"] == "offline" and seen["duty"]["on_duty"] is True
    assert seen["employee_number"] and seen["job_title"] == "Cashier"


# ---- 7. nobody changes their own permissions ----------------------------------------

def test_people_cannot_change_their_own_role_or_pay(owner):
    c = make_user(owner, "cashier")
    r = api("PUT", "/profile/me", c["token"], json={"phone": "0977 123456", "role_id": "owner", "basic_ngwee": 1})
    assert r.status_code == 200 and r.json()["role_id"] == "cashier"
    assert api("PATCH", f"/admin/users/{c['id']}", c["token"], json={"role_id": "owner"}).status_code == 403
    assert api("POST", f"/team/{c['id']}/restore", c["token"]).status_code in (403, 409)
    assert api("GET", "/team", c["token"]).status_code == 403


# ---- 8-9. owners manage accounts; suspension cuts access ----------------------------

def test_suspend_cuts_access_and_restore_gives_it_back(owner):
    c = make_user(owner, "cashier")
    r = api("POST", f"/team/{c['id']}/suspend", owner, json={"reason": "investigation"})
    assert r.status_code == 200 and r.json()["account"]["code"] == "suspended"
    assert api("GET", "/auth/me", c["token"]).status_code in (401, 403)
    assert api("POST", "/auth/login", json={"email": c["email"], "password": c["password"]}).status_code == 401
    r = api("POST", f"/team/{c['id']}/restore", owner)
    assert r.status_code == 200 and r.json()["account"]["code"] == "active"
    assert login(c["email"], c["password"])["token"]


def test_archived_people_leave_the_directory_but_not_the_records(owner):
    c = make_user(owner, "kitchen")
    assert api("POST", f"/team/{c['id']}/archive", owner, json={"reason": "left the business"}).status_code == 200
    assert c["id"] not in {p["id"] for p in api("GET", "/team", owner).json()}
    assert c["id"] in {p["id"] for p in api("GET", "/team?archived=true", owner).json()}


# ---- 10. sessions can be revoked -----------------------------------------------------

def test_one_device_can_be_signed_out_alone(owner):
    c = make_user(owner, "cashier")
    phone = login(c["email"], c["password"], ua="Mozilla/5.0 (Linux; Android 14) Chrome/120 Mobile")["token"]
    sessions = api("GET", f"/team/{c['id']}/sessions", owner).json()["open"]
    assert len(sessions) >= 2 and any(s["device"] == "Phone" for s in sessions)
    target = next(s for s in sessions if s["device"] == "Phone")
    assert api("POST", f"/team/{c['id']}/sessions/revoke", owner, json={"session_id": target["id"]}).json()["ended"] == 1
    assert api("GET", "/auth/me", phone).status_code == 401
    assert api("GET", "/auth/me", c["token"]).status_code == 200
    # And a person can sign out their own other devices.
    other = login(c["email"], c["password"])["token"]
    assert api("POST", f"/team/{c['id']}/sessions/revoke", c["token"], json={}).json()["ended"] >= 1
    assert api("GET", "/auth/me", other).status_code == 401
    assert api("GET", "/auth/me", c["token"]).status_code == 200


def test_a_manager_cannot_see_sign_in_history(owner):
    m = make_user(owner, "manager")
    c = make_user(owner, "cashier")
    assert api("GET", f"/team/{c['id']}", m["token"]).status_code == 200
    assert api("GET", f"/team/{c['id']}/logins", m["token"]).status_code == 403
    assert api("GET", f"/team/{c['id']}/sessions", m["token"]).status_code == 403
    assert api("POST", f"/team/{c['id']}/sessions/revoke", m["token"], json={}).status_code == 403


# ---- 11. profile changes are audited, without secrets ----------------------------------

def test_profile_changes_are_audited_without_passwords(owner):
    c = make_user(owner, "cashier")
    api("PUT", "/profile/me", c["token"], json={"phone": "0966 555 444"})
    with SessionLocal() as db:
        row = db.scalar(select(AuditLog).where(AuditLog.actor == c["name"], AuditLog.action == "Own profile changed")
                        .order_by(AuditLog.at.desc()))
        assert row and "0966" in (row.after or "")
        everything = " ".join(f"{a.detail} {a.before} {a.after}" for a in db.scalars(
            select(AuditLog).where(AuditLog.actor == c["name"])).all())
        assert c["password"] not in everything


# ---- 12. confidential information stays protected ---------------------------------------

def test_cashiers_cannot_read_each_others_details(owner):
    a = make_user(owner, "cashier")
    b = make_user(owner, "cashier")
    for tab in ("", "/payroll", "/logins", "/employment", "/activity", "/sessions"):
        assert api("GET", f"/team/{b['id']}{tab}", a["token"]).status_code == 403, tab
    assert api("GET", f"/profile/photo/{b['id']}", a["token"]).status_code == 403


# ---- 13. the shared counter: lock, unlock, switch person --------------------------------

def test_locked_screen_refuses_work_until_the_same_person_unlocks(owner):
    c = make_user(owner, "cashier")
    other = make_user(owner, "cashier")
    assert api("POST", "/auth/lock", c["token"]).status_code == 200
    assert api("GET", "/sales/orders", c["token"]).status_code == 423
    assert api("POST", "/auth/unlock", c["token"], json={"password": other["password"]}).status_code == 401
    assert api("POST", "/auth/unlock", c["token"], json={"password": c["password"]}).status_code == 200
    assert api("GET", "/sales/orders", c["token"]).status_code == 200
    # Handing over: this device's session ends; the next person signs in as themselves.
    assert api("POST", "/auth/logout", c["token"], json={"switch": True}).status_code == 200
    assert api("GET", "/sales/orders", c["token"]).status_code == 401


# ---- two-step sign-in ----------------------------------------------------------------------

def test_two_step_sign_in(owner):
    c = make_user(owner, "accountant")
    setup = api("POST", "/auth/two-step/start", c["token"]).json()
    assert api("POST", "/auth/two-step/confirm", c["token"], json={"code": "000000"}).status_code == 400
    done = api("POST", "/auth/two-step/confirm", c["token"], json={"code": twostep.code_now(setup["secret"])})
    assert done.status_code == 200 and len(done.json()["recovery_codes"]) == 8
    first = login(c["email"], c["password"])
    assert first["needs_code"] and not first["token"]
    # The ticket is not a sign-in.
    assert api("GET", "/auth/me", first["ticket"]).status_code == 401
    assert api("POST", "/auth/login/code", json={"ticket": first["ticket"], "code": "123456"}).status_code == 401
    ok = api("POST", "/auth/login/code", json={"ticket": first["ticket"], "code": twostep.code_now(setup["secret"])})
    assert ok.status_code == 200 and ok.json()["token"]
    # A recovery code works once.
    code = done.json()["recovery_codes"][0]
    again = login(c["email"], c["password"])
    assert api("POST", "/auth/login/code", json={"ticket": again["ticket"], "code": code}).status_code == 200
    again = login(c["email"], c["password"])
    assert api("POST", "/auth/login/code", json={"ticket": again["ticket"], "code": code}).status_code == 401


def test_owners_must_set_up_two_step(owner):
    second = make_user(owner, "owner")
    try:
        with SessionLocal() as db:
            db.execute(update(Setting).where(Setting.key == "signin.fill_passwords").values(value="false"))
            db.commit()
        token = login(second["email"], second["password"])["token"]
        me = api("GET", "/auth/me", token).json()
        assert me["user"]["two_step_required"] is True
        assert api("GET", "/team", token).status_code == 428
        setup = api("POST", "/auth/two-step/start", token).json()
        assert api("POST", "/auth/two-step/confirm", token, json={"code": twostep.code_now(setup["secret"])}).status_code == 200
        assert api("GET", "/team", token).status_code == 200
        assert api("POST", "/auth/two-step/off", token, json={"password": second["password"],
                                                              "code": twostep.code_now(setup["secret"])}).status_code == 409
    finally:
        with SessionLocal() as db:
            db.execute(update(Setting).where(Setting.key == "signin.fill_passwords").values(value="true"))
            db.commit()
        switch_off(second["id"])


# ---- notices to the owners -------------------------------------------------------------------

def test_owners_hear_about_accounts_and_lockouts(owner):
    second = make_user(owner, "owner")
    try:
        made = make_user(second["token"], "cashier")
        notes = api("GET", "/notifications", owner).json()
        assert any(made["name"] in n["title"] for n in notes)
        for _ in range(5):
            api("POST", "/auth/login", json={"email": made["email"], "password": "wrong-one"})
        notes = api("GET", "/notifications", owner).json()
        assert any("sign-in locked" in n["title"] and made["name"] in n["title"] for n in notes)
        # Going online or offline is never a notice.
        assert not any("online" in n["title"].lower() for n in notes)
        assert api("POST", "/notifications/read", owner, json={"all": True}).status_code == 200
        assert api("POST", "/presence/heartbeat", owner, json={}).json()["unread"] == 0
    finally:
        switch_off(second["id"])


# ---- the owner's Team status card is real data -------------------------------------------------

def test_team_summary_counts_real_people(owner):
    summary = api("GET", "/team/summary", owner).json()
    with SessionLocal() as db:
        active = db.scalars(select(User).where(User.is_active.is_(True), User.archived_at.is_(None))).all()
    assert summary["registered"] == len(active)
    assert summary["online"] + summary["away"] + summary["lost"] + summary["offline"] == summary["registered"]
    assert any(p["presence"]["status"] in ("online", "away") for p in summary["connected"])
