"""One account for each kind of staff, so every card on the sign-in screen works.

    python -m app.starter_accounts

Makes the second owner account (owner2@greenbuffet.zm) if there is only one
owner, and one account for each other kind that has none yet (manager@...,
accountant@..., cashier@..., kitchen@...), with a temporary password, printed once. Each
person must choose their own password at their first sign-in. Roles that
already have an account are left alone, so running it twice changes nothing.

Rename the accounts to real people's names and emails under Staff & roles.
"""
import sys

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import generate_temp_password, hash_password
from app.models.access import Role, User
from app.services.audit import record

# The second owner is made here too: the business has two owners with equal
# authority, each with their own account (never a shared login).
STARTERS = [
    ("owner", "owner2@greenbuffet.zm", "Second owner"),
    ("manager", "manager@greenbuffet.zm", "Manager"),
    ("accountant", "accountant@greenbuffet.zm", "Accountant"),
    ("cashier", "cashier@greenbuffet.zm", "Cashier"),
    ("kitchen", "kitchen@greenbuffet.zm", "Kitchen"),
    ("it", "it@greenbuffet.zm", "IT support"),
]


def main() -> int:
    made = []
    with SessionLocal() as db:
        for role_id, email, name in STARTERS:
            if not db.get(Role, role_id):
                continue
            wanted = 2 if role_id == "owner" else 1
            have = len(db.scalars(select(User.id).where(User.role_id == role_id, User.is_active.is_(True))).all())
            if have >= wanted:
                print(f"  {name:<14} already has an account, left alone")
                continue
            existing = db.scalar(select(User).where(User.email == email))
            password = generate_temp_password()
            if existing:
                existing.role_id, existing.is_active = role_id, True
                existing.password_hash = hash_password(password)
                existing.must_change_password = True
            else:
                db.add(User(name=name, email=email, role_id=role_id, password_hash=hash_password(password),
                            is_active=True, must_change_password=True, created_by="starter accounts"))
            record(db, "server computer", "users", "Account created", f"{email} ({role_id}) by starter-accounts")
            made.append((name, email, password))
        db.commit()

    if made:
        print()
        print("  New accounts. Write these down; the passwords are not shown again.")
        print("  Each person chooses their own password the first time they sign in.")
        print()
        for name, email, password in made:
            print(f"  {name:<14} {email:<30} {password}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
