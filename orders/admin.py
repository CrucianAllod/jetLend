from django.contrib import admin
from django.http import HttpRequest

from common.admin import MoneyDisplayMixin
from orders.models import Order, OrderItem


class OrderItemInline(MoneyDisplayMixin, admin.TabularInline):  # type: ignore[type-arg]
    """Display immutable order lines inside an order page."""

    model = OrderItem
    extra = 0
    can_delete = False
    fields = (
        "product",
        "product_name",
        "quantity",
        "unit_price",
        "subtotal",
        "discount",
        "total",
    )
    readonly_fields = fields

    @admin.display(description="Цена")
    def unit_price(self, obj: OrderItem) -> str:
        return self._format_money(obj.unit_price_minor)

    @admin.display(description="До скидки")
    def subtotal(self, obj: OrderItem) -> str:
        return self._format_money(obj.subtotal_minor)

    @admin.display(description="Скидка")
    def discount(self, obj: OrderItem) -> str:
        return self._format_money(obj.discount_minor)

    @admin.display(description="Итого")
    def total(self, obj: OrderItem) -> str:
        return self._format_money(obj.total_minor)

    def has_add_permission(
        self,
        request: HttpRequest,
        obj: Order | None = None,
    ) -> bool:
        return False


@admin.register(Order)
class OrderAdmin(MoneyDisplayMixin, admin.ModelAdmin):  # type: ignore[type-arg]
    """Provide read-only order inspection with formatted monetary totals."""

    list_display = (
        "id",
        "user",
        "status",
        "promo_code",
        "subtotal",
        "discount",
        "total",
        "created_at",
    )
    list_filter = ("status", "created_at")
    list_select_related = ("user", "promo_code")
    search_fields = ("id", "user__username", "user__email", "promo_code__code")
    readonly_fields = (
        "user",
        "status",
        "promo_code",
        "subtotal_minor",
        "discount_minor",
        "total_minor",
        "created_at",
        "updated_at",
    )
    date_hierarchy = "created_at"
    inlines = (OrderItemInline,)

    @admin.display(description="До скидки", ordering="subtotal_minor")
    def subtotal(self, obj: Order) -> str:
        return self._format_money(obj.subtotal_minor)

    @admin.display(description="Скидка", ordering="discount_minor")
    def discount(self, obj: Order) -> str:
        return self._format_money(obj.discount_minor)

    @admin.display(description="Итого", ordering="total_minor")
    def total(self, obj: Order) -> str:
        return self._format_money(obj.total_minor)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_delete_permission(
        self,
        request: HttpRequest,
        obj: Order | None = None,
    ) -> bool:
        return False


@admin.register(OrderItem)
class OrderItemAdmin(MoneyDisplayMixin, admin.ModelAdmin):  # type: ignore[type-arg]
    """Provide searchable read-only access to individual order lines."""

    list_display = (
        "id",
        "order",
        "product",
        "quantity",
        "subtotal",
        "discount",
        "total",
    )
    list_select_related = ("order", "product")
    search_fields = ("order__id", "product__name", "product_name")
    readonly_fields = (
        "order",
        "product",
        "product_name",
        "unit_price_minor",
        "quantity",
        "subtotal_minor",
        "discount_minor",
        "total_minor",
        "created_at",
    )

    @admin.display(description="До скидки", ordering="subtotal_minor")
    def subtotal(self, obj: OrderItem) -> str:
        return self._format_money(obj.subtotal_minor)

    @admin.display(description="Скидка", ordering="discount_minor")
    def discount(self, obj: OrderItem) -> str:
        return self._format_money(obj.discount_minor)

    @admin.display(description="Итого", ordering="total_minor")
    def total(self, obj: OrderItem) -> str:
        return self._format_money(obj.total_minor)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_delete_permission(
        self,
        request: HttpRequest,
        obj: OrderItem | None = None,
    ) -> bool:
        return False
