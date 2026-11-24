"""The permission catalogue and the FastAPI guards that enforce it.

Every protected endpoint declares what it needs. The check runs on the server
on every request, so hiding a button in the front end is never the only
protection.
"""
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_token
from app.models.access import User

# code, label, area, sort
PERMISSION_CATALOGUE: list[tuple[str, str, str, int]] = [
    ("pos.use", "Till and cash drawer", "Sales and service", 10),
    ("orders.view", "See orders", "Sales and service", 20),
    ("orders.update", "Move orders along", "Sales and service", 30),
    ("orders.cancel", "Cancel orders", "Sales and service", 40),
    ("kitchen.view", "Kitchen display", "Sales and service", 50),
    ("customers.view", "Customer list", "Sales and service", 80),
    ("customers.manage", "Change customers and stamp cards", "Sales and service", 85),
    ("discounts.give", "Give discounts up to the till limit", "Sales and service", 86),
    ("discounts.approve", "Approve discounts above the limit", "Sales and service", 87),
    ("refunds.request", "Ask for a refund", "Sales and service", 88),
    ("payments.confirm", "Confirm mobile money and card payments", "Sales and service", 89),
    ("cash.move", "Cash drops, petty cash and cash added", "Sales and service", 92),
    ("cash.approve", "Confirm cash movements and review till counts", "Sales and service", 94),
    ("service.control", "Pause orders and wait time", "Sales and service", 90),
    ("menu.edit", "Edit menu and prices", "Menu and stock", 100),
    ("promos.manage", "Promotions", "Menu and stock", 110),
    ("inventory.view", "See stock", "Menu and stock", 120),
    ("inventory.adjust", "Adjust stock", "Menu and stock", 130),
    ("purchases.manage", "Suppliers and purchases", "Menu and stock", 140),
    ("books.view", "See accounts and statements", "Accounting", 200),
    ("books.edit", "Record cash, bank, invoices, expenses", "Accounting", 210),
    ("accounts.manage", "Chart of accounts and bank accounts", "Accounting", 220),
    ("journal.post", "Prepare journals", "Accounting", 230),
    ("journal.approve", "Approve journals and voids", "Accounting", 240),
    ("assets.manage", "Fixed assets and depreciation", "Accounting", 250),
    ("reports.view", "Sales reports and payments", "Accounting", 260),
    ("hr.view", "See employees", "People", 300),
    ("hr.manage", "Manage employees and departments", "People", 310),
    ("payroll.view", "See payroll and payslips", "People", 320),
    ("payroll.manage", "Prepare payroll, loans, rates", "People", 330),
    ("payroll.approve", "Approve payroll", "People", 340),
    ("payroll.pay", "Record salary payments", "People", 350),
    ("attendance.clock", "Clock in and out, apply for leave", "People", 360),
    ("attendance.manage", "Rosters and attendance records", "People", 370),
    ("leave.approve", "Approve leave", "People", 380),
    ("staff.manage", "User accounts", "Administration", 400),
    ("roles.manage", "Roles and permissions", "Administration", 410),
    ("settings.edit", "System settings", "Administration", 420),
    ("audit.view", "Audit logs", "Administration", 430),
    ("feedback.view", "Customer feedback", "Administration", 440),
]

ALL_PERMISSIONS = [c for c, _, _, _ in PERMISSION_CATALOGUE]

OPS = [
    "pos.use", "orders.view", "orders.update", "orders.cancel", "kitchen.view",
    "customers.view", "customers.manage", "service.control",
    "discounts.give", "discounts.approve", "refunds.request", "payments.confirm",
    "cash.move", "cash.approve",
    "menu.edit", "promos.manage", "inventory.view", "inventory.adjust",
    "purchases.manage", "reports.view", "feedback.view",
]
FINANCE = [
    "books.view", "books.edit", "accounts.manage", "journal.post",
    "journal.approve", "assets.manage",
]
PEOPLE = [
    "hr.view", "hr.manage", "payroll.view", "payroll.manage", "payroll.approve",
    "payroll.pay", "attendance.clock", "attendance.manage", "leave.approve",
]
ADMIN = ["staff.manage", "roles.manage", "settings.edit", "audit.view"]

# Starting roles: the five account types of the business brief. The owners
# can change these, or make their own, on the Roles screen. "Administrator"
# and "Inventory staff" were retired at the owners' request (24 Nov 2026):
# their accounts became Manager and Kitchen accounts, and their work moved
# onto the owner, manager and kitchen screens.
DEFAULT_ROLES: dict[str, tuple[str, str, list[str]]] = {
    "owner": ("Owner", "Full access to everything", ALL_PERMISSIONS),
    "manager": (
        "Manager",
        "Day-to-day running, approvals at the till, stock, books and people; no payroll approval",
        OPS + ["books.view", "books.edit", "hr.view", "hr.manage", "payroll.view",
               "attendance.clock", "attendance.manage", "leave.approve", "audit.view"],
    ),
    "accountant": (
        "Accountant",
        "Books, statements, purchases, payroll and reconciling payments",
        ["orders.view", "reports.view", "inventory.view", "purchases.manage", "customers.view",
         "payments.confirm", "cash.approve"]
        + FINANCE
        + ["payroll.view", "payroll.manage", "payroll.approve", "payroll.pay",
           "hr.view", "attendance.clock", "audit.view"],
    ),
    "cashier": (
        "Cashier",
        "Till, payments, small discounts, refund requests, cash drops, own attendance",
        ["pos.use", "orders.view", "orders.update", "attendance.clock",
         "discounts.give", "refunds.request", "cash.move"],
    ),
    "kitchen": (
        "Kitchen staff",
        "Kitchen display, sold-out switches, stock counts and waste",
        ["kitchen.view", "orders.view", "orders.update", "inventory.view", "inventory.adjust",
         "service.control", "attendance.clock"],
    ),
}

# Retired roles and where their accounts go. Applied once by seed.py.
RETIRED_ROLES = {"admin": "manager", "inventory": "kitchen"}


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Reads the bearer token and returns the signed-in user, or refuses."""
    header = request.headers.get("Authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to continue.")
    payload = decode_token(header[7:].strip())
    if not payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your session has ended. Sign in again.")
    user = db.get(User, payload.get("sub"))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account is disabled.")
    if payload.get("v", 0) != (user.token_version or 0):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your session has ended. Sign in again.")
    return user


def requires(*codes: str):
    """Guard a route: requires('payroll.approve'). Any one of the codes is enough."""

    def guard(user: User = Depends(current_user)) -> User:
        allowed = set(user.role.permission_codes)
        if not any(c in allowed for c in codes):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"{user.role.label} accounts cannot do this.",
            )
        return user

    return guard
