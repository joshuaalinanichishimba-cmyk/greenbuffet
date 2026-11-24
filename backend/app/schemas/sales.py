"""Request and response shapes for the till.

Notice what the browser may send: which product, which options, how many. It
never sends a price. Everything with money in it is worked out on the server
from the menu as it stands at that moment.
"""
from pydantic import BaseModel, Field

from app.services.approvals import ApprovalIn


class ShiftOpenIn(BaseModel):
    float_ngwee: int = Field(default=0, ge=0, le=100_000_000)
    note: str = Field(default="", max_length=300)


class ShiftCloseIn(BaseModel):
    counted_ngwee: int = Field(ge=0, le=1_000_000_000)
    # Why the drawer is out, when it is out by more than the limit.
    note: str = Field(default="", max_length=300)


class ShiftReviewIn(BaseModel):
    note: str = Field(min_length=3, max_length=300)


class CashMoveIn(BaseModel):
    kind: str
    amount_ngwee: int = Field(gt=0, le=1_000_000_000)
    reason: str = Field(min_length=3, max_length=200)


class CashMoveOut(BaseModel):
    id: str
    shift_id: str
    cashier: str
    kind: str
    label: str
    amount_ngwee: int
    reason: str
    status: str
    recorded_by: str | None
    at: str
    decided_by: str | None


class DecideIn(BaseModel):
    ok: bool
    note: str = Field(default="", max_length=200)


class MethodTotal(BaseModel):
    method: str
    label: str
    amount_ngwee: int
    count: int


class ShiftOut(BaseModel):
    id: str
    opened_by: str
    opened_at: str
    float_ngwee: int
    closed_at: str | None
    closed_by: str | None
    expected_ngwee: int | None
    counted_ngwee: int | None
    variance_ngwee: int | None
    note: str
    is_open: bool
    orders: int
    sales_ngwee: int
    # Hidden (None) from a cashier while their own till is open, so the count
    # at closing is blind: they type what is in the drawer, not what the
    # screen says should be there.
    cash_ngwee: int | None
    by_method: list[MethodTotal]
    cash_moves_ngwee: int = 0
    first_count_ngwee: int | None = None
    reviewed_by: str | None = None
    review_note: str = ""
    needs_review: bool = False


class LineOptionIn(BaseModel):
    option_item_id: str


class OrderLineIn(BaseModel):
    product_id: str
    quantity: int = Field(default=1, ge=1, le=99)
    options: list[LineOptionIn] = []
    note: str = Field(default="", max_length=160)


class OrderIn(BaseModel):
    lines: list[OrderLineIn] = Field(min_length=1)
    order_type: str = "takeaway"
    customer_name: str = Field(default="", max_length=80)
    customer_phone: str = Field(default="", max_length=24)
    note: str = Field(default="", max_length=300)
    discount_ngwee: int = Field(default=0, ge=0, le=100_000_000)
    discount_reason: str = Field(default="", max_length=160)
    # A manager's email and password, typed at the till, when the discount
    # is above the cashier's limit.
    approval: ApprovalIn | None = None
    # A promotion code typed at the till. The server decides whether it
    # applies and what it is worth.
    promo_code: str = Field(default="", max_length=24)


class PaymentIn(BaseModel):
    method: str
    amount_ngwee: int = Field(gt=0, le=1_000_000_000)
    tendered_ngwee: int | None = Field(default=None, ge=0, le=1_000_000_000)
    reference: str = Field(default="", max_length=60)
    note: str = Field(default="", max_length=200)
    # Mobile money and card: the cashier has seen the operator's message
    # saying the money arrived. Without it the payment waits as pending.
    confirmed: bool = False


class RefundIn(BaseModel):
    method: str
    amount_ngwee: int = Field(gt=0, le=1_000_000_000)
    reason: str = Field(min_length=3, max_length=200)
    approval: ApprovalIn | None = None


class CancelIn(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


class LineOptionOut(BaseModel):
    group_name: str
    item_name: str
    price_ngwee: int
    option_item_id: str | None = None


class OrderLineOut(BaseModel):
    id: str
    product_id: str
    product_name: str
    product_code: str
    station: str
    unit_ngwee: int
    options_ngwee: int
    quantity: int
    line_ngwee: int
    note: str
    options: list[LineOptionOut]


class PaymentOut(BaseModel):
    id: str
    method: str
    label: str
    amount_ngwee: int
    tendered_ngwee: int | None
    change_ngwee: int | None
    reference: str
    is_refund: bool
    at: str
    taken_by: str | None
    status: str = "confirmed"
    confirmed_by: str | None = None


class OrderOut(BaseModel):
    id: str
    number: str
    status: str
    order_type: str
    customer_name: str
    customer_phone: str
    note: str
    subtotal_ngwee: int
    discount_ngwee: int
    discount_reason: str = ""
    discount_approved_by: str | None = None
    total_ngwee: int
    vat_ngwee: int
    paid_ngwee: int
    outstanding_ngwee: int
    change_ngwee: int
    created_by: str | None
    created_at: str
    paid_at: str | None
    cancelled_at: str | None
    cancel_reason: str
    lines: list[OrderLineOut]
    payments: list[PaymentOut]


class DayTotals(BaseModel):
    date: str
    orders: int
    sales_ngwee: int
    vat_ngwee: int
    refunds_ngwee: int
    by_method: list[MethodTotal]
