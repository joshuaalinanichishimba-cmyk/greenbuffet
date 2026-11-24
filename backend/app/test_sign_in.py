"""Test mode for the sign-in screen: tap a card, press Enter.

    python -m app.test_sign_in        switch it on
    python -m app.test_sign_in --off  switch it off

While the system is being tried out, typing passwords for seven kinds of
account gets in the way. Switched on, this gives every active account the
same test password and makes the sign-in screen fill it in, so a tap on a
card and Enter signs in, like the demo.

It refuses to run when ENVIRONMENT is production, and the server never
fills passwords in production even if the switch was left on. Before real
use: switch it off, then have everyone set their own password (Staff &
roles, reset password).
"""
import sys

from sqlalchemy import delete, select

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.access import LoginAttempt, Setting, User
from app.services.audit import record

TEST_PASSWORD = "greenbuffet2026"
KEY = "signin.fill_passwords"


def _set(db, value: str) -> None:
    row = db.get(Setting, KEY)
    if row:
        row.value = value
    else:
        db.add(Setting(key=KEY, value=value, label="Sign-in screen fills test passwords"))


def main() -> int:
    off = "--off" in sys.argv
    with SessionLocal() as db:
        if off:
            _set(db, "false")
            record(db, "server computer", "settings", "Test sign-in off", "Passwords are no longer filled in")
            db.commit()
            print("Test sign-in is off. Everyone types their password again.")
            print("Before real use, give each person their own password under Staff & roles.")
            return 0
        if settings.ENVIRONMENT == "production":
            print("Refused: this computer is set to production. Test sign-in is only for trying the system out.")
            return 1
        users = db.scalars(select(User).where(User.is_active.is_(True))).all()
        hashed = hash_password(TEST_PASSWORD)
        for u in users:
            u.password_hash = hashed
            u.must_change_password = False
        db.execute(delete(LoginAttempt).where(LoginAttempt.succeeded.is_(False)))
        _set(db, "true")
        record(db, "server computer", "settings", "Test sign-in on",
               f"{len(users)} accounts given the test password")
        db.commit()
    print(f"Test sign-in is on for {len(users)} accounts.")
    print(f"  Every account's password is now: {TEST_PASSWORD}")
    print("  On the sign-in screen, tap a card (and a name, if there are several) and press Enter.")
    print("  Switch it off before real use:  .\\scripts\\test-sign-in.ps1 -Off")
    return 0


if __name__ == "__main__":
    sys.exit(main())
