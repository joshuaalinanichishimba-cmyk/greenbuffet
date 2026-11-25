"""Request and response shapes for the access endpoints."""
from pydantic import BaseModel, EmailStr, Field


class LoginIn(BaseModel):
    # Deliberately a plain string, not EmailStr: signing in only looks the
    # address up. Rejecting an unusual-but-real address here would lock a
    # genuine user out with a confusing validation error.
    email: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=1)
    # The kind of account the person says they are signing in as. When given,
    # it has to match the account's role, so nobody ends up on the wrong
    # screens by accident (a manager signing in on the counter's cashier
    # login, say). Optional, so scripts and older screens still work.
    role_id: str | None = Field(default=None, max_length=40)


class UserOut(BaseModel):
    id: str
    name: str
    email: str
    role_id: str
    role_label: str
    is_active: bool
    must_change_password: bool
    photo_id: str | None = None
    totp_enabled: bool = False
    # An owner without two-step sign-in: the screens send them to set it up.
    two_step_required: bool = False


class LoginOut(BaseModel):
    token: str
    expires_at: str
    user: UserOut
    permissions: list[str]
    # The password was right and the account uses two-step sign-in: the
    # ticket goes back with the six-digit code to /auth/login/code.
    needs_code: bool = False
    ticket: str = ""
    session_id: str = ""


class CodeIn(BaseModel):
    ticket: str = Field(min_length=10, max_length=1000)
    code: str = Field(min_length=6, max_length=12)


class PasswordIn(BaseModel):
    password: str = Field(min_length=1, max_length=200)


class LogoutIn(BaseModel):
    # True when the person is handing the screen to someone else.
    switch: bool = False


class TwoStepConfirmIn(BaseModel):
    code: str = Field(min_length=6, max_length=12)


class TwoStepOffIn(BaseModel):
    password: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=6, max_length=12)


class PermissionOut(BaseModel):
    code: str
    label: str
    area: str


class RoleOut(BaseModel):
    id: str
    label: str
    description: str
    is_system: bool
    permissions: list[str]


class RoleUpdateIn(BaseModel):
    label: str | None = Field(default=None, max_length=60)
    permissions: list[str]


class RoleCreateIn(BaseModel):
    label: str = Field(min_length=3, max_length=60)
    description: str = Field(default="", max_length=200)
    permissions: list[str] = []


class UserCreateIn(BaseModel):
    name: str = Field(min_length=3, max_length=80)
    email: EmailStr
    role_id: str
    # Left out, the server invents a temporary one and returns it once.
    password: str | None = Field(default=None, min_length=8, max_length=100)


class UserCreateOut(UserOut):
    # Shown to the administrator once, to pass on to the new member of staff.
    temporary_password: str | None = None


class UserPatchIn(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=80)
    email: EmailStr | None = None
    role_id: str | None = None
    is_active: bool | None = None


class PasswordResetOut(BaseModel):
    user: UserOut
    temporary_password: str


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=100)
