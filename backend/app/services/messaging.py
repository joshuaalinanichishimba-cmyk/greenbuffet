"""Messages to customers, written down whether or not anything can send them.

The Green Buffet has no WhatsApp Business account and no SMS shortcode, and
getting either is an application to a company, not a line of code. So this
module does the half that can be done honestly: it writes every message the
system wants to send into a queue, with the exact words, the number, and what
it is about.

Two things follow from that. Staff can open the message list, read what should
go out and send it from the restaurant's own phone in ten seconds, which is
what they would have done anyway. And on the day a gateway is connected,
`send_queued` is the only function that has to change.

A message is never the reason a sale fails. Everything here swallows its own
errors: an order is more important than a notification about it.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.access import Setting
from app.models.customers import Message, normalise_phone
from app.services.money import kwacha


def _setting(db: Session, key: str, fallback: str) -> str:
    row = db.get(Setting, key)
    return row.value if row and row.value else fallback


def queue(
    db: Session,
    to_phone: str,
    body: str,
    about: str = "order",
    reference: str = "",
    to_name: str = "",
    channel: str = "whatsapp",
) -> Message | None:
    """Writes one message. Returns None rather than raising if it cannot."""
    phone = normalise_phone(to_phone)
    if not phone or not body.strip():
        return None
    try:
        message = Message(
            to_phone=phone, to_name=to_name[:80], channel=channel,
            body=body.strip(), about=about, reference=reference[:40], status="queued",
        )
        db.add(message)
        return message
    except Exception:
        return None


# ---------------------------------------------------------------------------
# the messages the system actually sends
# ---------------------------------------------------------------------------

def order_received(db: Session, order) -> Message | None:
    name = _setting(db, "business.name", "The Green Buffet")
    return queue(
        db, order.customer_phone,
        f"{name}: we have your order {order.number} for {kwacha(order.total_ngwee)}. "
        f"We will confirm it in a few minutes.",
        about="order", reference=order.number, to_name=order.customer_name,
    )


def order_accepted(db: Session, order, minutes: int) -> Message | None:
    name = _setting(db, "business.name", "The Green Buffet")
    when = f"about {minutes} minutes" if minutes else "shortly"
    where = "delivered to you" if order.fulfilment == "delivery" else "ready for collection"
    return queue(
        db, order.customer_phone,
        f"{name}: order {order.number} is confirmed. It will be {where} in {when}.",
        about="order", reference=order.number, to_name=order.customer_name,
    )


def order_rejected(db: Session, order, reason: str) -> Message | None:
    name = _setting(db, "business.name", "The Green Buffet")
    phones = _setting(db, "business.phones", "")
    tail = f" Call us on {phones.split(',')[0]} if you would like to change it." if phones else ""
    return queue(
        db, order.customer_phone,
        f"{name}: sorry, we cannot take order {order.number}. {reason}".strip() + tail,
        about="order", reference=order.number, to_name=order.customer_name,
    )


def order_ready(db: Session, order) -> Message | None:
    name = _setting(db, "business.name", "The Green Buffet")
    if order.fulfilment == "delivery":
        body = f"{name}: order {order.number} is on its way to you now."
    else:
        body = f"{name}: order {order.number} is ready for collection."
    return queue(db, order.customer_phone, body, about="order",
                 reference=order.number, to_name=order.customer_name)


def catering_quoted(db: Session, booking) -> Message | None:
    name = _setting(db, "business.name", "The Green Buffet")
    return queue(
        db, booking.customer_phone,
        f"{name}: your quote for {booking.number} is {kwacha(booking.quote_ngwee)}. "
        f"A deposit of {kwacha(booking.deposit_due_ngwee)} confirms the booking.",
        about="catering", reference=booking.number, to_name=booking.customer_name,
    )


def send_queued(db: Session, limit: int = 50) -> dict:
    """Sends what is waiting, once there is something to send it with.

    There is no gateway yet, so this marks nothing as sent and says so. The
    shape of the answer is the shape it will keep, which is what lets the
    screen that calls it be written now.
    """
    waiting = db.scalars(
        select(Message).where(Message.status == "queued").order_by(Message.created_at).limit(limit)
    ).all()
    return {
        "sent": 0,
        "waiting": len(waiting),
        "detail": (
            "No messaging account is connected yet, so nothing was sent. "
            "Open Messages to read what is waiting and send it from the "
            "restaurant phone."
        ),
    }


def mark_sent_by_hand(db: Session, message: Message, who: str | None) -> Message:
    message.status = "sent"
    message.sent_at = datetime.now(timezone.utc)
    message.sent_by = who
    return message
