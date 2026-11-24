"""Create the permission catalogue, the starting roles and the first owner account.

Safe to run more than once: it adds what is missing and leaves the rest alone.
Run from the backend/ folder:
    python -m app.seed
"""
import sys

from sqlalchemy import func, select

from app.core.config import settings
from app.core.database import SessionLocal, engine
from app.core.permissions import RETIRED_ROLES, DEFAULT_ROLES, PERMISSION_CATALOGUE
from app.core.schema_update import add_missing_columns, drop_retired
from app.core.security import generate_temp_password, hash_password
from app.models.access import Permission, Role, RolePermission, Setting, User
from app.models import Base  # registers every table
from app.services.posting import ensure_chart

DEFAULT_SETTINGS = [
    ("business.name", "The Green Buffet", "Business name"),
    ("business.location", "Liberty Mall", "Location"),
    ("business.phones", "0960554543,0972699005", "Order phone numbers"),
    ("business.currency", "ZMW", "Currency"),
    ("service.prep_minutes", "12", "Base preparation time (minutes)"),
    ("loyalty.enabled", "true", "Give stamps and the free bowl"),
    ("loyalty.stamps_needed", "8", "Paid bowls or burritos before one is free"),
    ("business.social", "@the.green.buffet", "Social handle"),
    ("business.whatsapp", "0960554543", "WhatsApp chat number"),
    ("menu.topping_charge_ngwee", "1000", "Charge per bowl topping over five (ngwee)"),
    ("hours.sun", "08:30-15:00", "Sunday"),
    ("hours.mon", "08:30-19:30", "Monday"),
    ("hours.tue", "08:30-19:30", "Tuesday"),
    ("hours.wed", "08:30-19:30", "Wednesday"),
    ("hours.thu", "08:30-19:30", "Thursday"),
    ("hours.fri", "08:30-19:30", "Friday"),
    ("hours.sat", "08:30-19:30", "Saturday"),
]

# Somewhere to start for delivery. Kitwe areas and real-ish fees, meant to be
# corrected on the Delivery screen rather than guessed at by the owner.


def mark_stamp_categories(db) -> list[str]:
    """Bowls and burritos earn stamps, as in the demo. Called only on the run
    that creates the earns_stamp column, whether seed or the server gets there
    first; after that the Menu screen decides."""
    from app.models.menu import Category

    marked = []
    for category in db.scalars(select(Category)).all():
        name = category.name.lower()
        if "bowl" in name or "burrito" in name:
            category.earns_stamp = True
            marked.append(category.name)
    db.commit()
    return marked


def seed(owner_email: str = "owner@greenbuffet.zm", owner_password: str | None = None) -> str:
    Base.metadata.create_all(engine)
    # A stage that adds a column to a table that already exists needs this;
    # create_all alone would leave the old table as it was.
    changed = add_missing_columns(engine)
    if changed:
        print(f"Database brought up to date: {', '.join(changed)}")
    # The retired customer-ordering tables and columns go, once. update.ps1
    # has taken a backup just before this runs.
    dropped = drop_retired(engine)
    if dropped:
        print(f"Removed (retired in stage 20, backup taken first): {', '.join(dropped)}")
    db = SessionLocal()
    # The run that introduces stamps marks bowls and burritos as earning
    # them, as the demo does. Only that run: afterwards it is the manager's
    # choice on the Menu screen, and an update must not undo it.
    if "categories.earns_stamp" in changed:
        for name in mark_stamp_categories(db):
            print(f"  {name}: earns stamps")
    created_password = owner_password or generate_temp_password()
    try:
        # The chart of accounts is part of a working system, like the roles.
        ensure_chart(db)
        existing = {p.code for p in db.scalars(select(Permission)).all()}
        brand_new = set()
        for code, label, area, sort in PERMISSION_CATALOGUE:
            if code not in existing:
                db.add(Permission(code=code, label=label, area=area, sort=sort))
                brand_new.add(code)
        db.flush()

        for role_id, (label, description, codes) in DEFAULT_ROLES.items():
            role = db.get(Role, role_id)
            if not role:
                role = Role(id=role_id, label=label, description=description, is_system=True)
                db.add(role)
                db.flush()
                for code in codes:
                    db.add(RolePermission(role_id=role_id, permission_code=code))

        # Retired roles: their people move to the role that now does that
        # work, then the role goes. Kitchen staff take on the store room's
        # counting, which is the only part of it they did not have.
        for old_id, new_id in RETIRED_ROLES.items():
            old_role = db.get(Role, old_id)
            if not old_role:
                continue
            moved = db.scalars(select(User).where(User.role_id == old_id)).all()
            for person in moved:
                person.role_id = new_id
            if old_id == "inventory":
                kitchen_held = {rp.permission_code for rp in db.scalars(
                    select(RolePermission).where(RolePermission.role_id == "kitchen")).all()}
                if "inventory.adjust" not in kitchen_held:
                    db.add(RolePermission(role_id="kitchen", permission_code="inventory.adjust"))
            for rp in db.scalars(select(RolePermission).where(RolePermission.role_id == old_id)).all():
                db.delete(rp)
            db.flush()
            db.delete(old_role)
            db.flush()
            from app.services.audit import record
            record(db, "Setup", "users", "Role retired",
                   f"{old_role.label}: {len(moved)} account(s) moved to {new_id}", old_id)
            print(f"  Role {old_role.label} retired: {len(moved)} account(s) now {new_id}")

        # A stage that introduces a permission has to give it to the roles that
        # should hold it, or the owner of a restaurant that has been running
        # for months would be locked out of a screen built for them. Only
        # codes that are new to the whole system are handed out, so a
        # permission an administrator deliberately removed stays removed.
        if brand_new:
            for role_id, (_, _, codes) in DEFAULT_ROLES.items():
                role = db.get(Role, role_id)
                if not role or not role.is_system:
                    continue
                held = {
                    rp.permission_code
                    for rp in db.scalars(
                        select(RolePermission).where(RolePermission.role_id == role_id)
                    ).all()
                }
                for code in brand_new & set(codes) - held:
                    db.add(RolePermission(role_id=role_id, permission_code=code))
                    print(f"  {role.label}: granted {code}")

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
