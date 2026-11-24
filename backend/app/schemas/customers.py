"""What the customer routes accept and return: regulars and their stamp cards."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


# ---- customers and points -------------------------------------------------

class CustomerOut(BaseModel):
    id: str
    phone: str
    name: str
    email: str
    area: str
    address: str
    note: str
    stamps: int
    stamps_needed: int
    free_ready: bool
    orders_count: int
    spent_ngwee: int
    last_order_at: str


class CustomerUpdateIn(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    email: str | None = Field(default=None, max_length=120)
    area: str | None = Field(default=None, max_length=80)
    address: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=300)


class PointsEntryOut(BaseModel):
    points: int
    balance_after: int
    reason: str
    at: str
    by: str


class PointsAdjustIn(BaseModel):
    points: int = Field(ge=-100_000, le=100_000)
    reason: str = Field(max_length=120)


# ---- delivery zones -------------------------------------------------------
