from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower


class PromoCode(models.Model):
    """Define a percentage promotion and its global usage restrictions."""

    code = models.CharField(max_length=64)
    discount_percent = models.PositiveSmallIntegerField(
        validators=(MinValueValidator(1), MaxValueValidator(100)),
    )
    expires_at = models.DateTimeField(db_index=True)
    max_uses = models.PositiveIntegerField(validators=(MinValueValidator(1),))
    used_count = models.PositiveIntegerField(default=0, editable=False)
    allowed_category = models.ForeignKey(
        "catalog.Category",
        on_delete=models.PROTECT,
        related_name="promo_codes",
        blank=True,
        null=True,
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("code", "id")
        constraints = (
            models.UniqueConstraint(
                Lower("code"),
                name="promocodes_code_case_insensitive_unique",
            ),
            models.CheckConstraint(
                condition=Q(discount_percent__gte=1) & Q(discount_percent__lte=100),
                name="promocodes_discount_percent_valid",
            ),
            models.CheckConstraint(
                condition=Q(max_uses__gt=0),
                name="promocodes_max_uses_positive",
            ),
            models.CheckConstraint(
                condition=Q(used_count__gte=0) & Q(used_count__lte=F("max_uses")),
                name="promocodes_used_count_valid",
            ),
        )
        verbose_name = "Промокод"
        verbose_name_plural = "Промокоды"

    def __str__(self) -> str:
        return self.code


class PromoCodeUsage(models.Model):
    """Record a successful promo-code use by a user for a single order."""

    promo_code = models.ForeignKey(
        PromoCode,
        on_delete=models.PROTECT,
        related_name="usages",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="promo_code_usages",
    )
    order = models.OneToOneField(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="promo_code_usage",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = (
            models.UniqueConstraint(
                fields=("promo_code", "user"),
                name="promocodes_usage_user_unique",
            ),
        )
        verbose_name = "Использование промокода"
        verbose_name_plural = "Использования промокодов"

    def __str__(self) -> str:
        return f"{self.promo_code_id}:{self.user_id}"
