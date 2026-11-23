"""Customer checkout records for the demonstration."""
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class DemoCheckout(Base, TimestampMixin):
    __tablename__ = "demo_checkouts"

    token: Mapped[str] = mapped_column(String(32), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), unique=True, nullable=False)
    payment_state: Mapped[str] = mapped_column(String(16), nullable=False)
