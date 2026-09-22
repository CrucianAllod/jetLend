from collections.abc import Sequence
from typing import ClassVar

from django.contrib import admin

from catalog.models import Category, Product
from common.admin import MoneyDisplayMixin


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Configure category search and slug generation in Django admin."""

    list_display = ("id", "name", "slug", "created_at")
    search_fields = ("name", "slug")
    prepopulated_fields: ClassVar[dict[str, Sequence[str]]] = {
        "slug": ("name",),
    }
    readonly_fields = ("created_at", "updated_at")


@admin.register(Product)
class ProductAdmin(MoneyDisplayMixin, admin.ModelAdmin):  # type: ignore[type-arg]
    """Expose product availability, promotion flags, and formatted prices."""

    list_display = (
        "id",
        "name",
        "category",
        "price",
        "is_active",
        "is_discount_excluded",
        "updated_at",
    )
    list_filter = ("is_active", "is_discount_excluded", "category")
    list_select_related = ("category",)
    search_fields = ("name", "category__name")
    autocomplete_fields = ("category",)
    readonly_fields = ("created_at", "updated_at")

    @admin.display(description="Цена", ordering="price_minor")
    def price(self, obj: Product) -> str:
        return self._format_money(obj.price_minor)
