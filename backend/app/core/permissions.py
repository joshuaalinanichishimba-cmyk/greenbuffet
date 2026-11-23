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
    ("dispatch.manage", "Delivery dispatch", "Sales and service", 60),
    ("catering.manage", "Catering bookings", "Sales and service", 70),
    ("customers.view", "Customer list", "Sales and service", 80),
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
    "dispatch.manage", "catering.manage", "customers.view", "service.control",
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

# Starting roles. Administrators can change these in the system afterwards.
DEFAULT_ROLES: dict[str, tuple[str, str, list[str]]] = {
    "owner": ("Owner", "Full access to everything", ALL_PERMISSIONS),
    "admin": ("Administrator", "Full access to everything", ALL_PERMISSIONS),
    "manager": (
        "Manager",
        "Day-to-day running, books and people, no payroll approval",
        OPS + ["books.view", "books.edit", "hr.view", "hr.manage", "payroll.view",
               "attendance.clock", "attendance.manage", "leave.approve", "audit.view"],
    ),
    "accountant": (
        "Accountant",
        "Books, statements, purchases and payroll",
        ["orders.view", "reports.view", "inventory.view", "purchases.manage", "customers.view"]
        + FINANCE
        + ["payroll.view", "payroll.manage", "payroll.approve", "payroll.pay",
           "hr.view", "attendance.clock", "audit.view"],
    ),
    "cashier": (
        "Cashier",
        "Till, collections and own attendance",
        ["pos.use", "orders.view", "orders.update", "dispatch.manage", "attendance.clock"],
    ),
    "kitchen": (
        "Kitchen staff",
        "Kitchen display, prep and sold-out switches",
        ["kitchen.view", "orders.view", "orders.update", "inventory.view",
         "service.control", "dispatch.manage", "attendance.clock"],
    ),
    "inventory": (
        "Inventory staff",
        "Stock, suppliers and purchases",
        ["orders.view", "inventory.view", "inventory.adjust", "purchases.manage",
         "attendance.clock"],
    ),
}


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
