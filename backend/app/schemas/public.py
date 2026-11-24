"""What the public routes accept and return.

These are deliberately narrow. A schema is the last line of defence on a route
that anyone on the internet can call, so every string has a length, every
number has a ceiling, and nothing a customer sends is allowed to be a list
long enough to be a weapon.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class PublicZone(BaseModel):
    id: str
    name: str
    fee_ngwee: int
    minutes: int
    minimum_ngwee: int


class ShopInfo(BaseModel):
    name: str
    location: str
    phones: list[str]
    accepting_orders: bool
    prep_minutes: int
    closed_message: str
    zones: list[PublicZone]


class PublicOptionItem(BaseModel):
    id: str
    name: str
    price_ngwee: int
    is_available: bool


class PublicOptionGroup(BaseModel):
    id: str
    name: str
    min_select: int
    max_select: int
    items: list[PublicOptionItem]


class PublicMenuProduct(BaseModel):
    id: str
    name: str
    description: str
    price_ngwee: int
    is_available: bool
    photo_id: str
    groups: list[PublicOptionGroup]


class PublicMenuCategory(BaseModel):
    id: str
    name: str
    description: str
    products: list[PublicMenuProduct]


class PublicMenu(BaseModel):
    categories: list[PublicMenuCategory]


class PublicLineOptionIn(BaseModel):
    option_item_id: str = Field(max_length=32)


class PublicLineIn(BaseModel):
    product_id: str = Field(max_length=32)
    quantity: int = Field(default=1, ge=1, le=20)
    options: list[PublicLineOptionIn] = Field(default=[], max_length=20)
    note: str = Field(default="", max_length=160)


class PublicOrderIn(BaseModel):
    # Twenty different items is a large office order; a hundred is an attack.
    lines: list[PublicLineIn] = Field(min_length=1, max_length=40)
    customer_name: str = Field(max_length=80)
    customer_phone: str = Field(max_length=24)
    fulfilment: str = Field(default="collection", max_length=12)
    area: str = Field(default="", max_length=80)
    address: str = Field(default="", max_length=200)
    directions: str = Field(default="", max_length=300)
    zone_id: str = Field(default="", max_length=32)
    note: str = Field(default="", max_length=300)


class PublicPlaced(BaseModel):
    number: str
    token: str
    total_ngwee: int


class PublicOrderOut(BaseModel):
    number: str
    token: str
    status: str
    fulfilment: str
    placed_at: str
    total_ngwee: int
    delivery_fee_ngwee: int
    customer_name: str
    address: str
    zone_name: str
    reject_reason: str
    minutes: int
    paid: bool
    lines: list[str]
