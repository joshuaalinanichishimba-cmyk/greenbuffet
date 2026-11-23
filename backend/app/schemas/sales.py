"""Request and response shapes for the till.

Notice what the browser may send: which product, which options, how many. It
never sends a price. Everything with money in it is worked out on the server
from the menu as it stands at that moment.
"""
from pydantic import BaseModel, Field


class ShiftOpenIn(BaseModel):
    float_ngwee: int = Field(default=0, ge=0, le=100_000_000)
    note: str = Field(default="", max_length=300)


class ShiftCloseIn(BaseModel):
    counted_ngwee: int = Field(ge=0, le=1_000_000_000)
    note: str = Field(default="", max_length=300)


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
    cash_ngwee: int
    by_method: list[MethodTotal]


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


class PaymentIn(BaseModel):
    method: str
    amount_ngwee: int = Field(gt=0, le=1_000_000_000)
    tendered_ngwee: int | None = Field(default=None, ge=0, le=1_000_000_000)
    reference: str = Field(default="", max_length=60)
    note: str = Field(default="", max_length=200)


class RefundIn(BaseModel):
    method: str
    amount_ngwee: int = Field(gt=0, le=1_000_000_000)
    reason: str = Field(min_length=3, max_length=200)


class CancelIn(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


class LineOptionOut(BaseModel):
    group_name: str
    item_name: str
    price_ngwee: int


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
