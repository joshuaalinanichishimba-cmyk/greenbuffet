"""Create the permission catalogue, the starting roles and the first owner account.

Safe to run more than once: it adds what is missing and leaves the rest alone.
Run from the backend/ folder:
    python -m app.seed
"""
import sys

from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal, engine
from app.core.permissions import DEFAULT_ROLES, PERMISSION_CATALOGUE
from app.core.security import generate_temp_password, hash_password
from app.models.access import Permission, Role, RolePermission, Setting, User
from app.models import Base  # registers every table
from app.services.posting import ensure_chart

DEFAULT_SETTINGS = [
    ("business.name", "The Green Buffet", "Business name"),
    ("business.location", "Liberty Mall", "Location"),
    ("business.phones", "0960554543,0972699005", "Order phone numbers"),
    ("business.currency", "ZMW", "Currency"),
    ("service.accepting_orders", "true", "Accepting online orders"),
    ("service.prep_minutes", "12", "Base preparation time (minutes)"),
]


def seed(owner_email: str = "owner@greenbuffet.zm", owner_password: str | None = None) -> str:
    Base.metadata.create_all(engine)
    db = SessionLocal()
    created_password = owner_password or generate_temp_password()
    try:
        # The chart of accounts is part of a working system, like the roles.
        ensure_chart(db)
        existing = {p.code for p in db.scalars(select(Permission)).all()}
        for code, label, area, sort in PERMISSION_CATALOGUE:
            if code not in existing:
                db.add(Permission(code=code, label=label, area=area, sort=sort))
        db.flush()

        for role_id, (label, description, codes) in DEFAULT_ROLES.items():
            role = db.get(Role, role_id)
            if not role:
                role = Role(id=role_id, label=label, description=description, is_system=True)
                db.add(role)
                db.flush()
                for code in codes:
                    db.add(RolePermission(role_id=role_id, permission_code=code))

        for key, value, label in DEFAULT_SETTINGS:
            if not db.get(Setting, key):
                db.add(Setting(key=key, value=value, label=label))

        owner = db.scalar(select(User).where(User.email == owner_email))
        if owner:
            created_password = ""
        else:
            db.add(User(
                name="Owner",
                email=owner_email,
                password_hash=hash_password(created_password),
                role_id="owner",
                is_active=True,
                must_change_password=True,
                created_by="seed",
            ))
        db.commit()
    finally:
        db.close()
    return created_password


if __name__ == "__main__":
    email = sys.argv[1] if len(sys.argv) > 1 else "owner@greenbuffet.zm"
    pw = seed(email)
    print("Database ready.")
    print(f"  Environment : {settings.ENVIRONMENT}")
    if pw:
        print(f"  Owner login : {email}")
        print(f"  Password    : {pw}")
        print("  Change this password the first time you sign in.")
    else:
        print(f"  Owner login : {email} (already existed, password unchanged)")
