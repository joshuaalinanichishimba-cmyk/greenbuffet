"""Users, roles, permissions, sessions and the audit log.

Permissions are rows, not constants in code, so an administrator can change
what a role may do without a new deployment.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, new_id


class Role(Base, TimestampMixin):
    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    label: Mapped[str] = mapped_column(String(60), nullable=False)
    description: Mapped[str] = mapped_column(String(200), default="")
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    permissions: Mapped[list["RolePermission"]] = relationship(
        back_populates="role", cascade="all, delete-orphan", lazy="selectin"
    )
    users: Mapped[list["User"]] = relationship(back_populates="role")

    @property
    def permission_codes(self) -> list[str]:
        return sorted(p.permission_code for p in self.permissions)


class Permission(Base):
    """The full catalogue of things that can be allowed."""

    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    area: Mapped[str] = mapped_column(String(40), nullable=False)
    sort: Mapped[int] = mapped_column(Integer, default=0)


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_code", name="uq_role_permission"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    permission_code: Mapped[str] = mapped_column(ForeignKey("permissions.code"), nullable=False)

    role: Mapped[Role] = relationship(back_populates="permissions")


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    email: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Every sign-in token carries this number. Raising it ends every session
    # the account has open: after a password reset, a password change, or
    # switching the account off.
    token_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- the profile (stage 23) ---
    # A phone for people with no staff-list record; for those with one, the
    # staff record's phone is the one shown and kept.
    phone: Mapped[str] = mapped_column(String(24), default="", nullable=False)
    photo_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Which optional notices this person wants, as JSON. Security notices
    # about their own account are always sent.
    preferences: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    # Why the account was suspended, shown to managers, never to the public.
    suspended_reason: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    # Archived accounts are switched off and hidden from the directory, but
    # every record they made stays, attributed to them.
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Two-step sign-in with an authenticator app (RFC 6238 codes). The secret
    # never leaves the server after setup; recovery codes are stored hashed.
    totp_secret: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    recovery_codes: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    # Email (stage 25). An address only receives sign-in codes and reset links
    # once its owner has proved they read it.
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # "app" or "email": how the second step is done. An authenticator app, if
    # set up, is always accepted as well.
    two_step_method: Mapped[str] = mapped_column(String(10), default="", nullable=False)

    role: Mapped[Role] = relationship(back_populates="users", lazy="selectin")


class UserSession(Base):
    """One sign-in on one device, from sign-in until it ends.

    The token carries this row's id, so a single device can be signed out
    without touching the others. Presence comes from the heartbeat each open
    screen sends: "seen" means the device is connected, "active" means
    someone touched it. Nothing about what is typed or shown is kept.
    """

    __tablename__ = "user_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # The screen was closed on purpose (the browser said so as it closed).
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Locked at the counter: the token is refused until the person unlocks.
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    # signed_out, switched, revoked, password, suspended, archived
    end_reason: Mapped[str] = mapped_column(String(20), default="", nullable=False)
    ended_by: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    device: Mapped[str] = mapped_column(String(20), default="", nullable=False)
    browser: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    ip: Mapped[str] = mapped_column(String(60), default="", nullable=False)


class Notification(Base):
    """A notice for one person: an account or security event that needs eyes.

    Routine comings and goings are never sent; they show on the directory.
    """

    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    level: Mapped[str] = mapped_column(String(10), default="info", nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    body: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    # Where to look: a profile, the directory, security settings.
    link: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LoginAttempt(Base):
    """Every sign-in try, so repeated failures can be spotted and slowed down."""

    __tablename__ = "login_attempts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False)
    ip: Mapped[str] = mapped_column(String(60), default="")
    # The browser and device, for the sign-in history. Never the password.
    device: Mapped[str] = mapped_column(String(80), default="", nullable=False)


class AuditLog(Base):
    """Append-only. Rows are never updated or deleted."""

    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(80), nullable=False)
    area: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    detail: Mapped[str] = mapped_column(String(300), default="")
    reference: Mapped[str] = mapped_column(String(60), default="")
    before: Mapped[str | None] = mapped_column(Text, nullable=True)
    after: Mapped[str | None] = mapped_column(Text, nullable=True)


Index("ix_audit_area_at", AuditLog.area, AuditLog.at)


class Setting(Base):
    """Business settings as key/value rows, editable without a deployment."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    label: Mapped[str] = mapped_column(String(120), default="")


class EmailChallenge(Base):
    """A one-time code or link sent by email: to sign in, to prove an address,
    to change it, or to reset a password.

    Only a keyed hash of the code is kept. A challenge works once, for a few
    minutes, for a few tries, and a new one for the same purpose cancels the
    old.
    """

    __tablename__ = "email_challenges"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    # sign_in, verify, change_old, change_new, reset
    purpose: Mapped[str] = mapped_column(String(12), nullable=False)
    email: Mapped[str] = mapped_column(String(160), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Links the old-address and new-address codes of one email change.
    group_id: Mapped[str] = mapped_column(String(32), default="", nullable=False)


class EmailMessage(Base):
    """Every email the system tried to send: to whom, why, and whether it
    went. Never the body, so no code or link is ever kept here."""

    __tablename__ = "email_messages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    to: Mapped[str] = mapped_column(String(160), nullable=False)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)
    subject: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)   # sent, failed, skipped
    error: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    provider: Mapped[str] = mapped_column(String(20), default="", nullable=False)
    ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
