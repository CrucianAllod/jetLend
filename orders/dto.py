from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OrderGoodResult:
    """Represent one calculated order line returned by the application layer."""

    good_id: int
    quantity: int
    price_minor: int
    discount_percent: int
    total_minor: int


@dataclass(frozen=True, slots=True)
class OrderResult:
    """Represent a successfully created order for response serialization."""

    user_id: int
    order_id: int
    goods: tuple[OrderGoodResult, ...]
    price_minor: int
    discount_percent: int
    total_minor: int
