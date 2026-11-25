"""Made-up trade for the online demo, so a visitor sees a restaurant at work.

    python -m app.demo_data

Runs ONLY when ENVIRONMENT is "demo". It refuses on the restaurant's own
computer (development) and on a real server (production), so it can never
mix invented sales into real books.

What it makes, the first time:
    named accounts for every role, all with the test password, on the
    sign-in cards; the staff list with jobs, pay and clocking; a week of
    sales through the real till (orders, payments in cash, mobile money and
    card, kitchen tickets, the books, stock used), each day in its own till
    session, opened in the morning and counted out at night.

Every time it starts (the demo server sleeps when unused and wakes on the
next visit) it tops up the days since it last ran, up to the current time,
so "today" is never empty. Every sale goes through the same code as a real
one, so the books balance; only the clock is moved back afterwards.
"""
from __future__ import annotations

import random
import sys
import uuid
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import DateTime, select, update

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.access import Setting, User
from app.models.base import Base
from app.models.books import JournalEntry
from app.models.people import Attendance, Employee, LeaveRequest

LUSAKA = timezone(timedelta(hours=2))
PASSWORD = "greenbuffet2026"
MARK = "demo.loaded_through"

# Invented people. None of them is a real member of staff.
PEOPLE = [
    # role, email, name, job title, department, basic pay (K)
    ("owner", "owner@greenbuffet.zm", "Chanda Mwale", "Owner", "Management", 0),
    ("owner", "owner2@greenbuffet.zm", "Natasha Banda", "Owner", "Management", 0),
    ("manager", "manager@greenbuffet.zm", "Mutale Phiri", "Restaurant manager", "Management", 9500),
    ("accountant", "accountant@greenbuffet.zm", "Grace Tembo", "Accountant", "Finance", 8000),
    ("cashier", "cashier@greenbuffet.zm", "Mwila Zulu", "Cashier", "Counter", 4200),
    ("cashier", "bupe@greenbuffet.zm", "Bupe Lungu", "Cashier", "Counter", 4200),
    ("kitchen", "kitchen@greenbuffet.zm", "Kelvin Sakala", "Head cook", "Kitchen", 5600),
    ("kitchen", "ruth@greenbuffet.zm", "Ruth Mbewe", "Cook", "Kitchen", 4500),
    ("it", "it@greenbuffet.zm", "Daniel Chileshe", "IT support", "Technical", 6000),
]
CUSTOMERS = ["Thandiwe", "Mapalo", "Chilufya", "Kondwani", "Natasha", "Bwalya", "Musonda", "Lubono", "Mulenga",
             "Chipo", "Wezi", "Kabwe", "Precious", "Mwape", "Joseph", "Esther", "Daniel", "Ruth", "Peter", ""]
# Moved back in time with each sale: everything a sale writes.
SALE_TABLES = ("orders", "order_lines", "order_line_options", "payments", "kitchen_items", "journal_entries",
               "journal_lines", "stock_moves", "points_entries", "cash_movements")
DAYS_BACK = 7


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _local(d: date, hour: float) -> datetime:
    return datetime.combine(d, time(0), LUSAKA) + timedelta(hours=hour)


def _shift_written(db, t0: datetime, t1: datetime, delta: timedelta) -> None:
    """Moves every timestamp written between t0 and t1 back by delta."""
    for je in db.scalars(select(JournalEntry).where(JournalEntry.posted_at >= t0, JournalEntry.posted_at <= t1)).all():
        je.entry_date = (je.posted_at + delta).astimezone(LUSAKA).date()
    db.flush()
    for table in Base.metadata.sorted_tables:
        if table.name not in SALE_TABLES:
            continue
        for col in table.columns:
            if isinstance(col.type, DateTime):
                db.execute(update(table).where(col >= t0, col <= t1).values({col.name: col + delta}))
    db.commit()


class Till:
    """The real API, called the way the till screen calls it."""

    def __init__(self):
        from fastapi.testclient import TestClient

        from app.main import app
        self.client = TestClient(app)
        self.tokens: dict[str, str] = {}

    def token(self, email: str) -> str:
        if email not in self.tokens:
            r = self.client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
            r.raise_for_status()
            self.tokens[email] = r.json()["token"]
        return self.tokens[email]

    def call(self, method: str, path: str, email: str, json=None, key: bool = False):
        headers = {"Authorization": f"Bearer {self.token(email)}"}
        if key:
            headers["Idempotency-Key"] = str(uuid.uuid4())
        r = self.client.request(method, "/api/v1" + path, headers=headers, json=json)
        if r.status_code >= 400:
            raise RuntimeError(f"{method} {path}: {r.status_code} {r.text[:300]}")
        return r.json()

    def finish(self) -> None:
        """Signs the script out, so it does not show on the Team page as a person online."""
        for email in list(self.tokens):
            try:
                self.call("POST", "/auth/logout", email, {})
            except RuntimeError:
                pass


def _people(db) -> None:
    for role, email, name, job, dept, pay in PEOPLE:
        user = db.scalar(select(User).where(User.email == email))
        if not user:
            user = User(email=email, role_id=role, name=name, password_hash=hash_password(PASSWORD),
                        is_active=True, must_change_password=False, created_by="demo")
            db.add(user)
            db.flush()
        user.name, user.role_id, user.is_active = name, role, True
        user.password_hash = hash_password(PASSWORD)
        user.must_change_password = False
        if not db.scalar(select(Employee).where(Employee.user_id == user.id)):
            from app.services.numbering import numbered
            number = numbered(db, "GB", width=3)
            while db.scalar(select(Employee.id).where(Employee.number == number)):
                number = numbered(db, "GB", width=3)
            db.add(Employee(number=number, name=name, job_title=job, department=dept, basic_ngwee=pay * 100,
                            phone=f"097{random.randint(1000000, 9999999)}", user_id=user.id,
                            start_date=date(2026, random.randint(1, 9), random.randint(1, 28)),
                            created_by="demo"))
    for key, value, label in (("signin.fill_passwords", "true", "Sign-in screen fills test passwords"),
                              ("signin.show_accounts", "true", "Sign-in cards list the accounts"),
                              # Visitors come and go; a screen locking itself mid-look would only confuse.
                              ("lock.after_minutes", "0", "Lock a screen after minutes without use")):
        row = db.get(Setting, key)
        if row:
            row.value = value
        else:
            db.add(Setting(key=key, value=value, label=label))
    db.commit()


def _menu(till: Till) -> list[dict]:
    products = till.call("GET", "/menu/products", "manager@greenbuffet.zm")
    return [p for p in products if p["is_active"] and p.get("is_available", True)]


def _line(product: dict) -> dict:
    """One menu item with sensible choices: the minimum each group needs, sometimes a little more."""
    options = []
    for group in product.get("option_groups", []):
        items = [i for i in group.get("options", group.get("items", [])) if i.get("is_active", True)]
        if not items:
            continue
        want = group.get("min_select", 0)
        if group.get("max_select", 1) > want and random.random() < 0.45:
            want += 1
        for item in random.sample(items, min(want, len(items))):
            options.append({"option_item_id": item["id"]})
    return {"product_id": product["id"], "quantity": 1 if random.random() < 0.85 else 2, "options": options}


def _sale(till: Till, cashier: str, menu: list[dict], pending_ok: bool) -> dict:
    lines = [_line(random.choice(menu)) for _ in range(random.choice((1, 1, 1, 2, 2, 3)))]
    body = {"order_type": random.choice(("takeaway", "takeaway", "eat_in")), "lines": lines,
            "customer_name": random.choice(CUSTOMERS)}
    if random.random() < 0.06:
        body.update(discount_ngwee=500, discount_reason="Regular customer",
                    approval={"email": "manager@greenbuffet.zm", "password": PASSWORD})
    order = till.call("POST", "/sales/orders", cashier, body, key=True)
    total = order["total_ngwee"]
    method = random.choices(("cash", "mtn", "airtel", "card", "zamtel"), (52, 22, 14, 8, 4))[0]
    pay = {"method": method, "amount_ngwee": total}
    if method == "cash":
        pay["tendered_ngwee"] = -(-total // 5000) * 5000
    else:
        pay["reference"] = ("MP" if method == "mtn" else "AT" if method == "airtel" else "TX") + uuid.uuid4().hex[:9].upper()
        pay["confirmed"] = not (pending_ok and random.random() < 0.25)
    return till.call("POST", f"/sales/orders/{order['id']}/payments", cashier, pay, key=True)


OPEN_AT, CLOSE_AT = 7.5, 20.5


def _hour(at: datetime, d: date) -> float:
    return (at.astimezone(LUSAKA) - _local(d, 0)).total_seconds() / 3600


def _day(db, till: Till, menu: list[dict], d: date, lo: float, hi: float, live: bool) -> int:
    """Trade on day d between hours lo and hi (Lusaka time). live: this is
    today up to now, so the newest orders stay on the kitchen board, some
    mobile money waits to be matched, and the tills stay open."""
    busy = 0.9 + (0.35 if d.weekday() in (4, 5) else 0) + random.uniform(-0.15, 0.15)
    rota = [("cashier@greenbuffet.zm", OPEN_AT)]
    if d.weekday() in (4, 5):
        rota.append(("bupe@greenbuffet.zm", 11.0))
    made = 0
    for cashier, start in rota:
        first = max(lo, start)
        if first >= hi:
            continue
        shift = till.call("GET", "/sales/shifts/current", cashier)
        if not shift:
            t0 = _now()
            shift = till.call("POST", "/sales/shifts", cashier, {"float_ngwee": 50000}, key=True)
            _shift_written(db, t0, _now(), _local(d, first) - _now())
        # Sales cluster at breakfast, lunch and the early evening.
        times = []
        for peak, spread, share in ((8.2, .7, 8), (12.8, 1.1, 20), (17.8, 1.2, 14)):
            for _ in range(int(share * busy / len(rota))):
                h = random.gauss(peak, spread)
                if first <= h <= hi and OPEN_AT <= h <= CLOSE_AT:
                    times.append(h)
        times.sort()
        for i, h in enumerate(times):
            newest = live and i >= len(times) - 3
            t0 = _now()
            order = _sale(till, cashier, menu, pending_ok=live)
            steps = ("preparing", "ready", "served")
            if newest:
                steps = () if i == len(times) - 1 else ("preparing",) if i == len(times) - 2 else ("preparing", "ready")
            for step in steps:
                till.call("POST", f"/kitchen/tickets/{order['id']}/status", "kitchen@greenbuffet.zm", {"status": step})
            _shift_written(db, t0, _now(), _local(d, h) - _now())
            made += 1
        if not live:
            listed = till.call("GET", "/sales/shifts?limit=100", "manager@greenbuffet.zm")
            s = next(x for x in listed if x["id"] == shift["id"])
            expected = s["float_ngwee"] + (s["cash_ngwee"] or 0) + s.get("cash_moves_ngwee", 0)
            short = random.random() < 0.15
            body = {"counted_ngwee": expected - (2500 if short else 0)}
            if short:
                body["note"] = "Busy lunch, I think I gave too much change once."
            t0 = _now()
            till.call("POST", f"/sales/shifts/{shift['id']}/close", cashier, body)
            _shift_written(db, t0, _now(), _local(d, CLOSE_AT + .3) - _now())
    return made


def _clocking(db, d: date, today: bool) -> None:
    for role, email, *_ in PEOPLE:
        if role in ("owner",):
            continue
        user = db.scalar(select(User).where(User.email == email))
        emp = db.scalar(select(Employee).where(Employee.user_id == user.id))
        if not emp or db.scalar(select(Attendance.id).where(Attendance.employee_id == emp.id, Attendance.day == d)):
            continue
        if d.weekday() == 6 and role in ("accountant",):
            continue
        start = 7.0 + random.uniform(-.2, .5) if role != "accountant" else 8.5 + random.uniform(0, .4)
        clock_in = _local(d, start)
        if today and clock_in > _now():
            continue
        clock_out = None if today else _local(d, start + random.uniform(8.5, 10))
        db.add(Attendance(employee_id=emp.id, day=d, clock_in=clock_in, clock_out=clock_out))
    db.commit()


def main() -> int:
    if settings.ENVIRONMENT != "demo":
        print("Refused: this only runs on the online demo (ENVIRONMENT=demo). It would put made-up sales in real books.")
        return 1
    random.seed()
    with SessionLocal() as db:
        _people(db)
        # DEMO_CLOCK_OFFSET_HOURS lets a test pretend it is later in the day.
        import os
        now = _now() + timedelta(hours=float(os.environ.get("DEMO_CLOCK_OFFSET_HOURS", "0")))
        today = now.astimezone(LUSAKA).date()
        mark = db.get(Setting, MARK)
        try:
            through = datetime.fromisoformat(mark.value) if mark and mark.value else None
        except ValueError:
            through = None
        if through is None or through < now - timedelta(days=DAYS_BACK):
            through = _local(today - timedelta(days=DAYS_BACK), 0)
        if now - through < timedelta(minutes=20):
            print("Demo data is up to date.")
            return 0
        till = Till()
        menu = _menu(till)
        if not menu:
            print("The menu is empty: run app.seed_menu first.")
            return 1
        # Tickets left on the board from the last visit were collected long ago.
        for ticket in till.call("GET", "/kitchen/tickets", "kitchen@greenbuffet.zm"):
            for step in ("preparing", "ready", "served"):
                try:
                    till.call("POST", f"/kitchen/tickets/{ticket['order_id']}/status", "kitchen@greenbuffet.zm",
                              {"status": step})
                except RuntimeError:
                    pass
        for older in db.scalars(select(Attendance).where(Attendance.clock_out.is_(None), Attendance.day < today)).all():
            older.clock_out = older.clock_in + timedelta(hours=9)
        db.commit()

        d = through.astimezone(LUSAKA).date()
        while d <= today:
            live = d == today
            lo = _hour(through, d) if d == through.astimezone(LUSAKA).date() else 0
            hi = min(CLOSE_AT, _hour(now, d) - 0.05) if live else 24
            made = _day(db, till, menu, d, max(0.0, lo), hi, live)
            _clocking(db, d, live)
            print(f"  {d.isoformat()}: {made} sales")
            d += timedelta(days=1)

        # Something for the managers to act on today.
        try:
            if not till.call("GET", "/sales/cash?pending=true", "manager@greenbuffet.zm"):
                till.call("POST", "/sales/cash", "cashier@greenbuffet.zm",
                          {"kind": "drop", "amount_ngwee": 40000, "reason": "To the safe after lunch"}, key=True)
        except RuntimeError:
            pass  # no till open yet this early in the day
        emp = db.scalar(select(Employee).join(User, User.id == Employee.user_id).where(User.email == "ruth@greenbuffet.zm"))
        if emp and not db.scalar(select(LeaveRequest.id).where(LeaveRequest.employee_id == emp.id)):
            db.add(LeaveRequest(employee_id=emp.id, kind="annual", start=today + timedelta(days=9),
                                end=today + timedelta(days=11), days=3, reason="Family wedding in Ndola"))
        till.finish()
        if mark:
            mark.value = now.isoformat()
        else:
            db.add(Setting(key=MARK, value=now.isoformat(), label="Demo trade made up to"))
        db.commit()
    print("Demo data ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
