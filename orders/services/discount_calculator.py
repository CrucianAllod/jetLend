from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DiscountLineInput:
    """Contain all product attributes needed for a pure discount calculation."""

    good_id: int
    unit_price_minor: int
    quantity: int
    category_id: int
    is_discount_excluded: bool


@dataclass(frozen=True, slots=True)
class DiscountLineResult:
    """Contain calculated monetary values for one order line."""

    good_id: int
    unit_price_minor: int
    quantity: int
    discount_percent: int
    subtotal_minor: int
    discount_minor: int
    total_minor: int


@dataclass(frozen=True, slots=True)
class DiscountCalculationResult:
    """Contain line-level calculations and aggregated order totals."""

    lines: tuple[DiscountLineResult, ...]
    discount_percent: int
    subtotal_minor: int
    discount_minor: int
    total_minor: int
    eligible_goods_count: int

    @property
    def has_eligible_goods(self) -> bool:
        return self.eligible_goods_count > 0


class DiscountCalculator:
    """Calculate category-aware percentage discounts without I/O or ORM access."""

    MIN_DISCOUNT_PERCENT = 0
    MAX_DISCOUNT_PERCENT = 100

    @classmethod
    def calculate(
        cls,
        lines: Sequence[DiscountLineInput],
        *,
        discount_percent: int = 0,
        allowed_category_id: int | None = None,
    ) -> DiscountCalculationResult:
        """Calculate every line and aggregate order totals in minor units."""

        cls._validate(discount_percent=discount_percent, lines=lines)

        calculated_lines: list[DiscountLineResult] = []
        eligible_goods_count = 0

        for line in lines:
            subtotal_minor = line.unit_price_minor * line.quantity
            is_eligible = cls._is_eligible(
                line,
                discount_percent=discount_percent,
                allowed_category_id=allowed_category_id,
            )
            line_discount_percent = discount_percent if is_eligible else 0

            if is_eligible:
                eligible_goods_count += 1

            discount_minor = cls._calculate_discount_minor(
                subtotal_minor,
                line_discount_percent,
            )
            calculated_lines.append(
                DiscountLineResult(
                    good_id=line.good_id,
                    unit_price_minor=line.unit_price_minor,
                    quantity=line.quantity,
                    discount_percent=line_discount_percent,
                    subtotal_minor=subtotal_minor,
                    discount_minor=discount_minor,
                    total_minor=subtotal_minor - discount_minor,
                )
            )

        subtotal_minor = sum(line.subtotal_minor for line in calculated_lines)
        discount_minor = sum(line.discount_minor for line in calculated_lines)

        return DiscountCalculationResult(
            lines=tuple(calculated_lines),
            discount_percent=discount_percent,
            subtotal_minor=subtotal_minor,
            discount_minor=discount_minor,
            total_minor=subtotal_minor - discount_minor,
            eligible_goods_count=eligible_goods_count,
        )

    @classmethod
    def _validate(
        cls,
        *,
        discount_percent: int,
        lines: Sequence[DiscountLineInput],
    ) -> None:
        if not cls.MIN_DISCOUNT_PERCENT <= discount_percent <= cls.MAX_DISCOUNT_PERCENT:
            msg = "Discount percent must be between 0 and 100."
            raise ValueError(msg)
        if not lines:
            msg = "At least one order line is required."
            raise ValueError(msg)

        for line in lines:
            if line.unit_price_minor < 0:
                msg = "Unit price cannot be negative."
                raise ValueError(msg)
            if line.quantity <= 0:
                msg = "Quantity must be greater than zero."
                raise ValueError(msg)

    @staticmethod
    def _is_eligible(
        line: DiscountLineInput,
        *,
        discount_percent: int,
        allowed_category_id: int | None,
    ) -> bool:
        if discount_percent == 0 or line.is_discount_excluded:
            return False
        return allowed_category_id is None or line.category_id == allowed_category_id

    @staticmethod
    def _calculate_discount_minor(
        subtotal_minor: int,
        discount_percent: int,
    ) -> int:
        return (subtotal_minor * discount_percent + 50) // 100
