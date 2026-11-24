"""User accounts, roles and permissions, and the audit log."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import ALL_PERMISSIONS, PERMISSION_CATALOGUE, current_user, requires
from app.core.security import generate_temp_password, hash_password
from app.models.access import AuditLog, LoginAttempt, Permission, Role, RolePermission, User
from app.schemas.access import (
    PasswordResetOut, PermissionOut, RoleCreateIn, RoleOut, RoleUpdateIn, UserCreateIn,
    UserCreateOut, UserOut, UserPatchIn,
)
from app.services.audit import record

router = APIRouter(prefix="/admin", tags=["admin"])


def _role_out(role: Role) -> RoleOut:
    return RoleOut(
        id=role.id,
        label=role.label,
        description=role.description,
        is_system=role.is_system,
        permissions=role.permission_codes,
    )


def _user_out(u: User) -> UserOut:
    return UserOut(
        id=u.id, name=u.name, email=u.email, role_id=u.role_id,
        role_label=u.role.label, is_active=u.is_active,
        must_change_password=u.must_change_password,
    )


@router.get("/permissions", response_model=list[PermissionOut])
def permissions(db: Session = Depends(get_db), _: User = Depends(requires("roles.manage", "staff.manage"))):
    rows = db.scalars(select(Permission).order_by(Permission.sort)).all()
    return [PermissionOut(code=p.code, label=p.label, area=p.area) for p in rows]


@router.get("/roles", response_model=list[RoleOut])
def roles(db: Session = Depends(get_db), _: User = Depends(requires("roles.manage", "staff.manage"))):
    return [_role_out(r) for r in db.scalars(select(Role).order_by(Role.label)).all()]


@router.post("/roles", response_model=RoleOut, status_code=status.HTTP_201_CREATED)
def create_role(body: RoleCreateIn, db: Session = Depends(get_db), user: User = Depends(requires("roles.manage"))):
    role_id = "".join(ch if ch.isalnum() else "-" for ch in body.label.strip().lower()).strip("-")[:40]
    if not role_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Give the role a name.")
    if db.get(Role, role_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "A role with that name already exists.")
    bad = [p for p in body.permissions if p not in ALL_PERMISSIONS]
    if bad:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown permission: {bad[0]}")

    role = Role(id=role_id, label=body.label.strip(), description=body.description, is_system=False)
    db.add(role)
    db.flush()
    for code in dict.fromkeys(body.permissions):
        db.add(RolePermission(role_id=role.id, permission_code=code))
    record(db, user.name, "security", "Role created", role.label, role.id, after=body.permissions)
    db.commit()
    db.refresh(role)
    return _role_out(role)


@router.put("/roles/{role_id}", response_model=RoleOut)
def update_role(role_id: str, body: RoleUpdateIn, db: Session = Depends(get_db), user: User = Depends(requires("roles.manage"))):
    role = db.get(Role, role_id)
    if not role:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not found.")
    codes = list(dict.fromkeys(body.permissions))
    bad = [p for p in codes if p not in ALL_PERMISSIONS]
    if bad:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown permission: {bad[0]}")

    # Nobody may lock themselves, or the last administrator, out of role management.
    if role_id == "owner" and "roles.manage" not in codes:
        raise HTTPException(status.HTTP_409_CONFLICT, "Owner and administrator must keep role management.")
    if user.role_id == role_id and "roles.manage" not in codes:
        raise HTTPException(status.HTTP_409_CONFLICT, "You cannot remove role management from your own role.")

    before = role.permission_codes
    role.permissions.clear()
    db.flush()
    for code in codes:
        db.add(RolePermission(role_id=role.id, permission_code=code))
    if body.label:
        role.label = body.label.strip()
    record(db, user.name, "security", "Role permissions changed", role.label, role.id, before=before, after=codes)
    db.commit()
    db.refresh(role)
    return _role_out(role)


@router.get("/users", response_model=list[UserOut])
def users(db: Session = Depends(get_db), _: User = Depends(requires("staff.manage"))):
    return [_user_out(u) for u in db.scalars(select(User).order_by(User.name)).all()]


@router.post("/users", response_model=UserCreateOut, status_code=status.HTTP_201_CREATED)
def create_user(body: UserCreateIn, db: Session = Depends(get_db), user: User = Depends(requires("staff.manage"))):
    email = body.email.strip().lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "That email already has an account.")
    if not db.get(Role, body.role_id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose a role.")
    temporary = body.password or generate_temp_password()
    created = User(
        name=body.name.strip(), email=email, role_id=body.role_id,
        password_hash=hash_password(temporary), must_change_password=True,
        created_by=user.name,
    )
    db.add(created)
    # Failed attempts are tracked by email, so an address someone mistyped into
    # the login form before this account existed would otherwise start it locked out.
    db.query(LoginAttempt).filter(LoginAttempt.email == email).delete()
    record(db, user.name, "security", "User account created", f"{created.name} as {body.role_id}", email)
    db.commit()
    db.refresh(created)
    # The password itself is never stored in the audit log, only handed back here.
    return UserCreateOut(**_user_out(created).model_dump(), temporary_password=temporary)


@router.patch("/users/{user_id}", response_model=UserOut)
def patch_user(user_id: str, body: UserPatchIn, db: Session = Depends(get_db), user: User = Depends(requires("staff.manage"))):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
    if target.id == user.id:
        if body.is_active is False:
            raise HTTPException(status.HTTP_409_CONFLICT, "You cannot disable your own account.")
        if body.role_id and body.role_id != target.role_id:
            new_role = db.get(Role, body.role_id)
            if not new_role or "staff.manage" not in new_role.permission_codes:
                raise HTTPException(status.HTTP_409_CONFLICT, "You cannot remove your own administrator access.")
    # Owners are equal, so neither can switch the other off or demote them
    # alone; and the business can never be left with no owner. (Both-owner
    # confirmation for this comes with the approval centre.)
    taking_away = (body.is_active is False) or (body.role_id is not None and body.role_id != "owner")
    if target.role_id == "owner" and taking_away:
        if target.id != user.id:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "One owner cannot switch off or demote the other. If an owner account is "
                "compromised, reset its password (that ends its sessions), or use "
                "scripts\\reset-owner.ps1 on the server computer.",
            )
        others = db.scalar(select(func.count(User.id)).where(
            User.role_id == "owner", User.is_active.is_(True), User.id != target.id)) or 0
        if not others:
            raise HTTPException(status.HTTP_409_CONFLICT, "The business must always have at least one active owner.")
    before = {"name": target.name, "email": target.email, "role": target.role_id, "active": target.is_active}
    if body.name:
        target.name = body.name.strip()
    if body.email:
        new_email = body.email.strip().lower()
        if new_email != target.email:
            if db.scalar(select(User).where(User.email == new_email, User.id != target.id)):
                raise HTTPException(status.HTTP_409_CONFLICT, "That email already has an account.")
            target.email = new_email
            db.query(LoginAttempt).filter(LoginAttempt.email == new_email).delete()
    if body.role_id:
        if not db.get(Role, body.role_id):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown role.")
        target.role_id = body.role_id
    if body.is_active is not None:
        if body.is_active is False and target.is_active:
            target.token_version = (target.token_version or 0) + 1
        target.is_active = body.is_active
    record(db, user.name, "security", "User account changed", target.name, target.email,
           before=before,
           after={"name": target.name, "email": target.email, "role": target.role_id, "active": target.is_active})
    db.commit()
    db.refresh(target)
    return _user_out(target)


@router.get("/audit")
def audit(
    area: str | None = None,
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(requires("audit.view")),
):
    stmt = select(AuditLog).order_by(AuditLog.at.desc()).limit(limit)
    if area:
        stmt = stmt.where(AuditLog.area == area)
    return [
        {
            "id": a.id, "at": a.at.isoformat(), "actor": a.actor, "area": a.area,
            "action": a.action, "detail": a.detail, "reference": a.reference,
            "before": a.before, "after": a.after,
        }
        for a in db.scalars(stmt).all()
    ]


@router.post("/users/{user_id}/reset-password", response_model=PasswordResetOut)
def reset_password(user_id: str, db: Session = Depends(get_db), user: User = Depends(requires("staff.manage"))):
    """Issues a temporary password and lifts any sign-in lockout on the account."""
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
    temporary = generate_temp_password()
    target.password_hash = hash_password(temporary)
    target.must_change_password = True
    target.token_version = (target.token_version or 0) + 1   # ends their open sessions
    # Failed attempts would otherwise keep the account locked out after the reset.
    db.query(LoginAttempt).filter(LoginAttempt.email == target.email).delete()
    record(db, user.name, "security", "Password reset", target.name, target.email)
    db.commit()
    db.refresh(target)
    return PasswordResetOut(user=_user_out(target), temporary_password=temporary)
