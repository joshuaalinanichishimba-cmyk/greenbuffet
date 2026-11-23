"""Request and response shapes for the menu endpoints.

Prices cross the wire as whole ngwee, the same way they are stored. The front
end formats them for display; no part of the system passes kwacha as a float.
"""
from pydantic import BaseModel, Field

from app.models.menu import UNITS


class CategoryIn(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    description: str = Field(default="", max_length=200)
    sort: int = Field(default=100, ge=0, le=9999)
    is_active: bool = True


class CategoryPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=60)
    description: str | None = Field(default=None, max_length=200)
    sort: int | None = Field(default=None, ge=0, le=9999)
    is_active: bool | None = None


class CategoryOut(BaseModel):
    id: str
    name: str
    description: str
    sort: int
    is_active: bool
    product_count: int


class OptionItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    price_ngwee: int = Field(default=0, ge=0, le=10_000_000)
    sort: int = Field(default=100, ge=0, le=9999)
    is_active: bool = True
    is_available: bool = True


class OptionItemOut(OptionItemIn):
    id: str
    group_id: str


class OptionGroupIn(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    helper: str = Field(default="", max_length=160)
    min_select: int = Field(default=0, ge=0, le=20)
    max_select: int = Field(default=1, ge=1, le=20)
    is_active: bool = True


class OptionGroupPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=60)
    helper: str | None = Field(default=None, max_length=160)
    min_select: int | None = Field(default=None, ge=0, le=20)
    max_select: int | None = Field(default=None, ge=1, le=20)
    is_active: bool | None = None


class OptionGroupOut(BaseModel):
    id: str
    name: str
    helper: str
    min_select: int
    max_select: int
    is_active: bool
    items: list[OptionItemOut]
    used_by: int


class ProductOptionOut(BaseModel):
    group_id: str
    name: str
    helper: str
    min_select: int
    max_select: int
    sort: int
    items: list[OptionItemOut]


class RecipeLineIn(BaseModel):
    ingredient_id: str
    quantity_milli: int = Field(gt=0, le=100_000_000)
    note: str = Field(default="", max_length=120)


class RecipeLineOut(RecipeLineIn):
    id: str
    ingredient_name: str
    unit: str
    cost_ngwee: int
    line_cost_ngwee: int
    # "180 g", "150 ml", "half" - what the kitchen would actually say
    quantity_label: str


class ProductIn(BaseModel):
    code: str = Field(min_length=2, max_length=24)
    name: str = Field(min_length=2, max_length=90)
    description: str = Field(default="", max_length=300)
    category_id: str
    price_ngwee: int = Field(ge=0, le=100_000_000)
    vat_rate: float = Field(default=16.0, ge=0, le=100)
    station: str = Field(default="kitchen", max_length=24)
    is_active: bool = True
    is_available: bool = True
    sort: int = Field(default=100, ge=0, le=9999)


class ProductPatch(BaseModel):
    code: str | None = Field(default=None, min_length=2, max_length=24)
    name: str | None = Field(default=None, min_length=2, max_length=90)
    description: str | None = Field(default=None, max_length=300)
    category_id: str | None = None
    price_ngwee: int | None = Field(default=None, ge=0, le=100_000_000)
    price_reason: str = Field(default="", max_length=200)
    vat_rate: float | None = Field(default=None, ge=0, le=100)
    station: str | None = Field(default=None, max_length=24)
    is_active: bool | None = None
    is_available: bool | None = None
    sort: int | None = Field(default=None, ge=0, le=9999)


class ProductOut(BaseModel):
    id: str
    code: str
    name: str
    description: str
    category_id: str
    category_name: str
    price_ngwee: int
    vat_rate: float
    station: str
    is_active: bool
    is_available: bool
    sort: int
    option_groups: list[ProductOptionOut]
    recipe: list[RecipeLineOut]
    recipe_cost_ngwee: int


class ProductGroupsIn(BaseModel):
    """The groups a product asks about, in the order given."""

    group_ids: list[str]


class IngredientIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    unit: str
    cost_ngwee: int = Field(default=0, ge=0, le=100_000_000)
    note: str = Field(default="", max_length=200)
    is_active: bool = True

    def validated_unit(self) -> str:
        if self.unit not in UNITS:
            raise ValueError(f"Unit must be one of: {', '.join(UNITS)}")
        return self.unit


class IngredientPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    unit: str | None = None
    cost_ngwee: int | None = Field(default=None, ge=0, le=100_000_000)
    note: str | None = Field(default=None, max_length=200)
    is_active: bool | None = None


class IngredientOut(BaseModel):
    id: str
    name: str
    unit: str
    cost_ngwee: int
    note: str
    is_active: bool
    used_in: int


class PriceChangeOut(BaseModel):
    id: str
    at: str
    product_id: str
    product_name: str
    old_ngwee: int
    new_ngwee: int
    reason: str
    changed_by: str | None
