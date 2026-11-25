"""Importing this package registers every table with SQLAlchemy."""
from app.models.access import (  # noqa: F401
    AuditLog, LoginAttempt, Notification, Permission, Role, RolePermission, Setting, User, UserSession,
)
from app.models.base import Base  # noqa: F401
from app.models.menu import (  # noqa: F401
    Category, Ingredient, OptionGroup, OptionItem, PriceChange, Product,
    ProductOptionGroup, RecipeLine,
)
from app.models.books import Account, JournalEntry, JournalLine  # noqa: F401
from app.models.business import Feedback, Promotion  # noqa: F401
from app.models.customers import Customer, PointsEntry  # noqa: F401
from app.models.files import Document  # noqa: F401
from app.services.numbering import Counter  # noqa: F401
from app.models.kitchen import KitchenItem  # noqa: F401
from app.models.people import Attendance, Employee, LeaveRequest, PayrollRun, Payslip  # noqa: F401
from app.models.stock import (  # noqa: F401
    Purchase, PurchaseLine, StockLevel, StockMove, Supplier, SupplierPayment,
)
from app.models.sales import (  # noqa: F401
    CashMovement, IdempotencyKey, Order, OrderLine, OrderLineOption, Payment, Shift,
)

__all__ = [
    "Base", "User", "UserSession", "Notification", "Role", "Permission", "RolePermission", "AuditLog", "LoginAttempt", "Setting",
    "Category", "Product", "OptionGroup", "OptionItem", "ProductOptionGroup",
    "Ingredient", "RecipeLine", "PriceChange",
    "Shift", "Order", "OrderLine", "OrderLineOption", "Payment", "IdempotencyKey",
    "KitchenItem", "Supplier", "StockLevel", "StockMove", "Purchase", "PurchaseLine", "SupplierPayment",
    "Account", "JournalEntry", "JournalLine",
    "Customer", "PointsEntry",
    "Promotion", "Feedback",
]
