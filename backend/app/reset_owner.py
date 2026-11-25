"""Give an account a new temporary password, from the server computer.

For when nobody can sign in: the owner's password is forgotten, or the only
administrator is locked out. It needs access to this computer and to
backend\\.env, which is the proof that whoever runs it is allowed to.

    python -m app.reset_owner                          the owner account
    python -m app.reset_owner someone@greenbuffet.zm   any account

It prints a new temporary password, switches the account back on, clears
the failed attempts that lock it for 15 minutes, and makes the person choose
their own password at the next sign-in. It also turns off two-step sign-in,
for a lost or replaced phone: an owner sets it up again straight after
signing in. Recorded in the activity log.
"""
import sys

from sqlalchemy import delete, select

from app.core.database import SessionLocal
from app.core.security import generate_temp_password, hash_password
from app.models.access import LoginAttempt, User
from app.services.audit import record


def reset(email: str) -> str | None:
    email = email.strip().lower()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            return None
        password = generate_temp_password()
        user.password_hash = hash_password(password)
        user.token_version = (user.token_version or 0) + 1  # ends any session still open
        user.must_change_password = True
        user.is_active = True
        user.archived_at = None
        user.suspended_reason = ""
        had_two_step = user.totp_enabled
        user.totp_enabled, user.totp_secret, user.recovery_codes = False, "", "[]"
        from app.services.accounts import end_sessions
        end_sessions(db, user, "password", "server computer")
        db.execute(delete(LoginAttempt).where(LoginAttempt.email == email, LoginAttempt.succeeded.is_(False)))
        record(db, "server computer", "users", "Password reset",
               f"Temporary password set for {email} with reset-owner on the server computer"
               + ("; two-step sign-in turned off." if had_two_step else "."), user.id)
        db.commit()
        return password


def main() -> int:
    email = sys.argv[1] if len(sys.argv) > 1 else "owner@greenbuffet.zm"
    password = reset(email)
    if password is None:
        print(f"No account with the email {email}.")
        with SessionLocal() as db:
            emails = db.scalars(select(User.email).order_by(User.email)).all()
        if emails:
            print("Accounts that exist: " + ", ".join(emails))
        return 1
    print()
    print(f"  Sign in as : {email}")
    print(f"  Password   : {password}")
    print("  You will be asked to choose your own password straight away.")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
