import logging
from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from catalog.models import Product
from orders.dto import OrderGoodResult, OrderResult
from orders.exceptions import OrderCreationError, OrderErrorCode
from orders.models import Order, OrderItem
from orders.serializers import CreateOrderInputData, OrderGoodInputData
from orders.services.discount_calculator import (
    DiscountCalculator,
    DiscountLineInput,
)
from promocodes.models import PromoCode, PromoCodeUsage

if TYPE_CHECKING:
    from django.contrib.auth.models import User

logger = logging.getLogger(__name__)


class CreateOrderService:
    """Create an order atomically while enforcing promo-code business rules."""

    @classmethod
    def execute(cls, data: CreateOrderInputData) -> OrderResult:
        """Validate persisted state, create an order, and return its API result."""

        with transaction.atomic():
            return cls._execute(data)

    @classmethod
    def _execute(cls, data: CreateOrderInputData) -> OrderResult:
        user = cls._get_user(data["user_id"])
        products_by_id = cls._get_products(data["goods"])
        promo_code = cls._get_promo_code(data.get("promo_code"), user_id=user.pk)

        discount_lines: list[DiscountLineInput] = []
        for item in data["goods"]:
            product = products_by_id[item["good_id"]]
            discount_lines.append(
                DiscountLineInput(
                    good_id=item["good_id"],
                    unit_price_minor=product.price_minor,
                    quantity=item["quantity"],
                    category_id=product.category_id,
                    is_discount_excluded=product.is_discount_excluded,
                )
            )

        calculation = DiscountCalculator.calculate(
            discount_lines,
            discount_percent=promo_code.discount_percent if promo_code else 0,
            allowed_category_id=(
                promo_code.allowed_category_id if promo_code else None
            ),
        )

        if promo_code is not None and not calculation.has_eligible_goods:
            raise OrderCreationError(
                code=OrderErrorCode.PROMO_CODE_NOT_APPLICABLE,
                detail="Промокод не применяется ни к одному товару в заказе.",
            )

        order = Order.objects.create(
            user=user,
            promo_code=promo_code,
            subtotal_minor=calculation.subtotal_minor,
            discount_minor=calculation.discount_minor,
            total_minor=calculation.total_minor,
        )
        OrderItem.objects.bulk_create(
            [
                OrderItem(
                    order=order,
                    product=products_by_id[line.good_id],
                    product_name=products_by_id[line.good_id].name,
                    unit_price_minor=line.unit_price_minor,
                    quantity=line.quantity,
                    subtotal_minor=line.subtotal_minor,
                    discount_minor=line.discount_minor,
                    total_minor=line.total_minor,
                )
                for line in calculation.lines
            ]
        )

        if promo_code is not None:
            cls._record_promo_code_usage(
                promo_code=promo_code,
                user=user,
                order=order,
            )

        logger.info(
            "Order created: order_id=%s user_id=%s items=%s promo_code=%s "
            "subtotal_minor=%s discount_minor=%s total_minor=%s",
            order.pk,
            user.pk,
            len(calculation.lines),
            promo_code.code if promo_code else None,
            calculation.subtotal_minor,
            calculation.discount_minor,
            calculation.total_minor,
        )

        return OrderResult(
            user_id=user.pk,
            order_id=order.pk,
            goods=tuple(
                OrderGoodResult(
                    good_id=line.good_id,
                    quantity=line.quantity,
                    price_minor=line.unit_price_minor,
                    discount_percent=line.discount_percent,
                    total_minor=line.total_minor,
                )
                for line in calculation.lines
            ),
            price_minor=calculation.subtotal_minor,
            discount_percent=calculation.discount_percent,
            total_minor=calculation.total_minor,
        )

    @staticmethod
    def _get_user(user_id: int) -> User:
        user = get_user_model()._default_manager.filter(pk=user_id).first()
        if user is None:
            raise OrderCreationError(
                code=OrderErrorCode.USER_NOT_FOUND,
                detail="Пользователь не найден.",
            )
        return user

    @staticmethod
    def _get_products(
        goods: list[OrderGoodInputData],
    ) -> dict[int, Product]:
        good_ids = [item["good_id"] for item in goods]
        if not good_ids or len(good_ids) != len(set(good_ids)):
            raise OrderCreationError(
                code=OrderErrorCode.INVALID_REQUEST,
                detail="Список товаров пуст или содержит повторения.",
            )

        products = (
            Product.objects.select_for_update().filter(pk__in=good_ids).order_by("pk")
        )
        products_by_id = {product.pk: product for product in products}

        if len(products_by_id) != len(good_ids) or any(
            not product.is_active for product in products_by_id.values()
        ):
            raise OrderCreationError(
                code=OrderErrorCode.GOOD_UNAVAILABLE,
                detail="Один или несколько товаров не найдены или недоступны.",
            )
        return products_by_id

    @staticmethod
    def _get_promo_code(
        code: str | None,
        *,
        user_id: int,
    ) -> PromoCode | None:
        if code is None:
            return None

        promo_code = (
            PromoCode.objects.select_for_update()
            .filter(code__iexact=code.strip())
            .first()
        )
        if promo_code is None or not promo_code.is_active:
            raise OrderCreationError(
                code=OrderErrorCode.PROMO_CODE_NOT_FOUND,
                detail="Промокод не найден.",
            )
        if promo_code.expires_at <= timezone.now():
            raise OrderCreationError(
                code=OrderErrorCode.PROMO_CODE_EXPIRED,
                detail="Срок действия промокода истёк.",
            )
        if promo_code.used_count >= promo_code.max_uses:
            raise OrderCreationError(
                code=OrderErrorCode.PROMO_CODE_USAGE_LIMIT_REACHED,
                detail="Лимит использований промокода исчерпан.",
            )
        if PromoCodeUsage.objects.filter(
            promo_code=promo_code,
            user_id=user_id,
        ).exists():
            raise OrderCreationError(
                code=OrderErrorCode.PROMO_CODE_ALREADY_USED,
                detail="Пользователь уже применял этот промокод.",
            )
        return promo_code

    @staticmethod
    def _record_promo_code_usage(
        *,
        promo_code: PromoCode,
        user: User,
        order: Order,
    ) -> None:
        PromoCodeUsage.objects.create(
            promo_code=promo_code,
            user=user,
            order=order,
        )
        updated_rows = PromoCode.objects.filter(
            pk=promo_code.pk,
            used_count__lt=F("max_uses"),
        ).update(used_count=F("used_count") + 1)
        if updated_rows != 1:
            raise OrderCreationError(
                code=OrderErrorCode.PROMO_CODE_USAGE_LIMIT_REACHED,
                detail="Лимит использований промокода исчерпан.",
            )
