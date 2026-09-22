from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q


class Order(models.Model):
    """Persist immutable monetary totals for a customer order."""

    class Status(models.TextChoices):
        """Supported order lifecycle states."""

        CREATED = "created", "Создан"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="orders",
    )
    status = models.CharField(
        max_length=32,
        choices=Status,
        default=Status.CREATED,
    )
    promo_code = models.ForeignKey(
        "promocodes.PromoCode",
        on_delete=models.PROTECT,
        related_name="orders",
        blank=True,
        null=True,
    )
    subtotal_minor = models.PositiveBigIntegerField()
    discount_minor = models.PositiveBigIntegerField(default=0)
    total_minor = models.PositiveBigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = (
            models.CheckConstraint(
                condition=Q(discount_minor__lte=F("subtotal_minor")),
                name="orders_order_discount_not_above_subtotal",
            ),
            models.CheckConstraint(
                condition=Q(
                    total_minor=F("subtotal_minor") - F("discount_minor"),
                ),
                name="orders_order_total_consistent",
            ),
        )
        indexes = (
            models.Index(
                fields=("user", "-created_at"),
                name="orders_user_created_idx",
            ),
        )
        verbose_name = "Заказ"
        verbose_name_plural = "Заказы"

    def __str__(self) -> str:
        return f"Заказ #{self.pk}"


class OrderItem(models.Model):
    """Store a product snapshot and calculated totals for an order line."""

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.PROTECT,
        related_name="order_items",
    )
    product_name = models.CharField(max_length=255)
    unit_price_minor = models.PositiveBigIntegerField()
    quantity = models.PositiveIntegerField(validators=(MinValueValidator(1),))
    subtotal_minor = models.PositiveBigIntegerField()
    discount_minor = models.PositiveBigIntegerField(default=0)
    total_minor = models.PositiveBigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("id",)
        constraints = (
            models.UniqueConstraint(
                fields=("order", "product"),
                name="orders_item_product_unique",
            ),
            models.CheckConstraint(
                condition=Q(quantity__gt=0),
                name="orders_item_quantity_positive",
            ),
            models.CheckConstraint(
                condition=Q(discount_minor__lte=F("subtotal_minor")),
                name="orders_item_discount_not_above_subtotal",
            ),
            models.CheckConstraint(
                condition=Q(
                    total_minor=F("subtotal_minor") - F("discount_minor"),
                ),
                name="orders_item_total_consistent",
            ),
        )
        verbose_name = "Позиция заказа"
        verbose_name_plural = "Позиции заказа"

    def __str__(self) -> str:
        return f"{self.product_name} x {self.quantity}"
