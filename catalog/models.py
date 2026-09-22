from django.db import models
from django.db.models import Q


class Category(models.Model):
    """Group products and optionally limit a promo code to that group."""

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name", "id")
        verbose_name = "Категория"
        verbose_name_plural = "Категории"

    def __str__(self) -> str:
        return self.name


class Product(models.Model):
    """Represent an orderable catalog item with a price in minor units."""

    name = models.CharField(max_length=255)
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
    )
    price_minor = models.PositiveBigIntegerField()
    is_active = models.BooleanField(default=True)
    is_discount_excluded = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name", "id")
        constraints = (
            models.CheckConstraint(
                condition=Q(price_minor__gte=0),
                name="catalog_product_price_minor_non_negative",
            ),
        )
        verbose_name = "Товар"
        verbose_name_plural = "Товары"

    def __str__(self) -> str:
        return self.name
