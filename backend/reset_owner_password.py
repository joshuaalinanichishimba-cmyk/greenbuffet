"""Sets a new password for one account and clears the failed-attempt lockout.

Run it from the backend folder with the project's own Python:

    cd "D:\The Green Buffet\backend"
    .\.venv\Scripts\python.exe reset_owner_password.py

Pass an email and a password to change someone else, or choose your own:

    .\.venv\Scripts\python.exe reset_owner_password.py cashier@greenbuffet.zm NewPass123
"""
import sys

from app.core.database import SessionLocal
from app.core.security import generate_temp_password, hash_password
from app.models.access import LoginAttempt, User

email = (sys.argv[1] if len(sys.argv) > 1 else "owner@greenbuffet.zm").strip().lower()
new_password = sys.argv[2] if len(sys.argv) > 2 else generate_temp_password()

db = SessionLocal()
user = db.query(User).filter(User.email == email).first()
if user is None:
    print(f"No account found for {email}.")
    print("Accounts in the database:", ", ".join(u.email for u in db.query(User).all()) or "(none)")
    raise SystemExit(1)

user.password_hash = hash_password(new_password)
user.must_change_password = True
user.is_active = True
removed = db.query(LoginAttempt).delete()
db.commit()

print(f"Password reset for {email}")
print(f"Sign in with: {new_password}")
print(f"Cleared {removed} login attempt(s), so any lockout is lifted.")
print("You will be asked to choose your own password straight after signing in.")
