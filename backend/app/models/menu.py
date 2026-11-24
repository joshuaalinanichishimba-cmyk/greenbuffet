"""The menu: categories, products, option groups, ingredients and recipes.

Money is stored as a whole number of ngwee (100 ngwee = K1). Storing kwacha as
a decimal invites rounding drift once discounts, VAT and change are involved,
so every price in the system is an integer and the formatting happens on the
way out.

Nothing on the menu is ever deleted once it has been sold. Products and
options are retired instead, so an old receipt still shows what was bought and
what it cost at the time.
"""
from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, new_id

UNITS = ("g", "kg", "ml", "l", "each")


class Category(Base, TimestampMixin):
    """A section of the menu board: bowls, burritos, drinks, sides."""

    __tablename__ = "categories"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    sort: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Whether each item sold from this section earns a loyalty stamp. The demo
    # gives stamps for bowls and burritos, not for dips or drinks.
    earns_stamp: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    products: Mapped[list[Product]] = relationship(back_populates="category")


class Product(Base, TimestampMixin):
    """Something a customer can order: a bowl, a burrito, a smoothie, a side."""

    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(24), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(90), nullable=False)
    description: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    category_id: Mapped[str] = mapped_column(ForeignKey("categories.id"), nullable=False, index=True)
    price_ngwee: Mapped[int] = mapped_column(Integer, nullable=False)
    # Zambian VAT is included in the shelf price, so this records what share of
    # the price is tax rather than adding anything on top at the till.
    vat_rate: Mapped[float] = mapped_column(Numeric(5, 2), default=16.00, nullable=False)
    station: Mapped[str] = mapped_column(String(24), default="kitchen", nullable=False)
    # on the menu at all / available right now (sold out switches this one)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort: Mapped[int] = mapped_column(Integer, default=100, nullable=False)

    category: Mapped[Category] = relationship(back_populates="products", lazy="selectin")
    option_links: Mapped[list[ProductOptionGroup]] = relationship(
        back_populates="product", cascade="all, delete-orphan", lazy="selectin",
        order_by="ProductOptionGroup.sort",
    )
    recipe: Mapped[list[RecipeLine]] = relationship(
        back_populates="product", cascade="all, delete-orphan", lazy="selectin",
    )


class OptionGroup(Base, TimestampMixin):
    """A choice attached to a product: base, protein, toppings, sauce, size.

    min_select and max_select carry the rule the till and the website both
    enforce: pick exactly one base, up to three toppings, and so on.
    """

    __tablename__ = "option_groups"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    helper: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    min_select: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_select: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # "Five toppings included, K10 for each one after": the first free_count
    # picks cost what their items say, every pick beyond that adds extra_ngwee.
    # Nought means the group has no such rule.
    free_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    extra_ngwee: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    items: Mapped[list[OptionItem]] = relationship(
        back_populates="group", cascade="all, delete-orphan", lazy="selectin",
        order_by="OptionItem.sort",
    )
    product_links: Mapped[list[ProductOptionGroup]] = relationship(back_populates="group")


class OptionItem(Base, TimestampMixin):
    """One choice inside a group, with what it adds to the price."""

    __tablename__ = "option_items"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    group_id: Mapped[str] = mapped_column(ForeignKey("option_groups.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    price_ngwee: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort: Mapped[int] = mapped_column(Integer, default=100, nullable=False)

    group: Mapped[OptionGroup] = relationship(back_populates="items", lazy="selectin")
    recipe: Mapped[list[RecipeLine]] = relationship(
        back_populates="option_item", cascade="all, delete-orphan", lazy="selectin",
    )

    __table_args__ = (UniqueConstraint("group_id", "name", name="uq_option_item_name"),)


class ProductOptionGroup(Base):
    """Which groups a product asks about, and in what order."""

    __tablename__ = "product_option_groups"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    group_id: Mapped[str] = mapped_column(ForeignKey("option_groups.id"), nullable=False, index=True)
    sort: Mapped[int] = mapped_column(Integer, default=100, nullable=False)

    product: Mapped[Product] = relationship(back_populates="option_links")
    group: Mapped[OptionGroup] = relationship(back_populates="product_links", lazy="selectin")

    __table_args__ = (UniqueConstraint("product_id", "group_id", name="uq_product_group"),)


class Ingredient(Base, TimestampMixin):
    """A raw item the kitchen buys and uses: chicken breast, rice, avocado.

    Stock levels and purchases arrive in stage 6; what is needed now is the
    list itself and the cost per unit, so a recipe can price a dish.
    """

    __tablename__ = "ingredients"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    unit: Mapped[str] = mapped_column(String(8), nullable=False)
    cost_ngwee: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    note: Mapped[str] = mapped_column(String(200), default="", nullable=False)

    lines: Mapped[list[RecipeLine]] = relationship(back_populates="ingredient")


class RecipeLine(Base, TimestampMixin):
    """How much of an ingredient a product, or one option, uses.

    A line belongs to either a product or an option item, never both: the bowl
    uses 180 g of rice, and choosing grilled chicken adds 120 g of chicken.
    """

    __tablename__ = "recipe_lines"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id"), nullable=True, index=True)
    option_item_id: Mapped[str | None] = mapped_column(ForeignKey("option_items.id"), nullable=True, index=True)
    ingredient_id: Mapped[str] = mapped_column(ForeignKey("ingredients.id"), nullable=False, index=True)
    # Thousandths of the ingredient's unit, so 180 g is 180000 and half an
    # avocado is 500. Integers again, for the same reason as the money.
    quantity_milli: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str] = mapped_column(String(120), default="", nullable=False)

    product: Mapped[Product | None] = relationship(back_populates="recipe")
    option_item: Mapped[OptionItem | None] = relationship(back_populates="recipe")
    ingredient: Mapped[Ingredient] = relationship(back_populates="lines", lazy="selectin")


class PriceChange(Base, TimestampMixin):
    """Every price a product has ever had, kept for the record.

    The audit log records that a price changed; this table is what reports read
    when they need to know what something cost on a given day.
    """

    __tablename__ = "price_changes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    old_ngwee: Mapped[int] = mapped_column(Integer, nullable=False)
    new_ngwee: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
