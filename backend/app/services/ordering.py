"""Turning what someone asked for into priced order lines.

This is the one place that decides what an order costs, and it is shared by
the till and by the public website on purpose. A customer ordering on their
phone must be charged by the same code that charges a customer standing at the
counter, or the two will drift apart and the difference will be found in the
books weeks later.

Nothing here trusts the price the browser sends. The browser sends what was
chosen; the price comes from the database every time.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.menu import OptionItem, Product
from app.models.sales import Order, OrderLine, OrderLineOption


class OrderProblem(Exception):
    """Something about the request cannot be priced. `code` picks the HTTP status."""

    def __init__(self, message: str, code: int = 422):
        super().__init__(message)
        self.message = message
        self.code = code


@dataclass
class Priced:
    subtotal_ngwee: int
    vat_ngwee: int


def business_vat_rate(db: Session) -> int:
    """The VAT rate for new sales: 0 when the business is not VAT-registered."""
    from app.models.access import Setting
    registered = db.get(Setting, "tax.vat_registered")
    if registered and registered.value == "false":
        return 0
    rate = db.get(Setting, "vat_rate")
    try:
        return max(0, min(100, int(float(rate.value)))) if rate else 16
    except ValueError:
        return 16


def build_lines(db: Session, order: Order, wanted_lines) -> Priced:
    """Adds priced lines to `order` and returns the totals before discount.

    `wanted_lines` is any sequence of objects with `product_id`, `quantity`,
    `note` and `options` (each with `option_item_id`), which is what both the
    till schema and the public schema produce.
    """
    vat_rate = business_vat_rate(db)
    subtotal = 0
    vat_total = 0

    for position, wanted in enumerate(wanted_lines, start=1):
        product = db.get(Product, wanted.product_id)
        if not product or not product.is_active:
            raise OrderProblem("That item is not on the menu.")
        if not product.is_available:
            raise OrderProblem(f"{product.name} is sold out.", code=409)

        allowed_groups = {link.group_id: link.group for link in product.option_links}
        chosen: dict[str, list[OptionItem]] = {}
        options_total = 0
        for choice in wanted.options:
            item = db.get(OptionItem, choice.option_item_id)
            if not item or not item.is_active:
                raise OrderProblem("Unknown choice.")
            if item.group_id not in allowed_groups:
                raise OrderProblem(f"{item.name} is not offered with {product.name}.")
            if not item.is_available:
                raise OrderProblem(f"{item.name} is sold out.", code=409)
            chosen.setdefault(item.group_id, []).append(item)

        # Each group's own rule, checked here because the browser cannot be
        # trusted to have checked it.
        for group_id, group in allowed_groups.items():
            if not group.is_active:
                continue
            picked = len(chosen.get(group_id, []))
            if picked < group.min_select:
                raise OrderProblem(f"{product.name}: choose {group.min_select} from {group.name}.")
            if picked > group.max_select:
                raise OrderProblem(f"{product.name}: at most {group.max_select} from {group.name}.")

        # What each pick costs. Usually its own price; in a group with an
        # "N included" rule, every pick after the first N also carries the
        # group's extra charge (five toppings in the bowl, K10 each after).
        charged: dict[str, int] = {}
        for group_id, items in chosen.items():
            group = allowed_groups[group_id]
            for index, item in enumerate(items):
                extra = group.extra_ngwee if group.free_count and index >= group.free_count else 0
                charged[f"{group_id}:{index}"] = item.price_ngwee + (extra or 0)
        options_total = sum(charged.values())

        unit = product.price_ngwee
        line_total = (unit + options_total) * wanted.quantity
        # VAT is inside the price: K116 at 16% holds K16 of tax. The owner
        # sets whether the business is VAT-registered and at what rate
        # (Settings, Tax); an item marked 0% stays exempt either way.
        rate = vat_rate if float(product.vat_rate) > 0 else 0
        vat_total += round(line_total * rate / (100 + rate)) if rate else 0
        subtotal += line_total

        line = OrderLine(
            order_id=order.id, position=position, product_id=product.id,
            product_name=product.name, product_code=product.code, station=product.station,
            unit_ngwee=unit, options_ngwee=options_total, quantity=wanted.quantity,
            line_ngwee=line_total, vat_rate=rate, note=(wanted.note or "").strip(),
        )
        db.add(line)
        db.flush()
        for group_id, items in chosen.items():
            for index, item in enumerate(items):
                db.add(OrderLineOption(
                    line_id=line.id, option_item_id=item.id,
                    group_name=allowed_groups[group_id].name, item_name=item.name,
                    price_ngwee=charged[f"{group_id}:{index}"],
                ))

    return Priced(subtotal_ngwee=subtotal, vat_ngwee=vat_total)


def apply_totals(order: Order, priced: Priced, discount_ngwee: int = 0) -> None:
    """Sets the money on the order once its lines are priced.

    A discount reduces the VAT inside the price proportionally, because less
    was charged.
    """
    subtotal = priced.subtotal_ngwee
    discount = max(0, min(discount_ngwee, subtotal))
    food_total = subtotal - discount
    food_vat = round(priced.vat_ngwee * (food_total / subtotal)) if subtotal else 0

    order.subtotal_ngwee = subtotal
    order.discount_ngwee = discount
    order.total_ngwee = food_total
    order.vat_ngwee = food_vat
