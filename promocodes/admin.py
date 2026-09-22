from django.contrib import admin
from django.http import HttpRequest
from django.utils import timezone

from promocodes.models import PromoCode, PromoCodeUsage


class PromoCodeUsageInline(admin.TabularInline):  # type: ignore[type-arg]
    """Display immutable promo usage records inside a promo-code page."""

    model = PromoCodeUsage
    extra = 0
    can_delete = False
    fields = ("user", "order", "created_at")
    readonly_fields = fields
    show_change_link = True

    def has_add_permission(
        self,
        request: HttpRequest,
        obj: PromoCode | None = None,
    ) -> bool:
        return False


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Manage promo configuration while protecting the usage counter."""

    list_display = (
        "id",
        "code",
        "discount_percent",
        "allowed_category",
        "expires_at",
        "used_count",
        "max_uses",
        "remaining_uses",
        "is_available",
        "is_active",
    )
    list_filter = ("is_active", "allowed_category", "expires_at")
    list_select_related = ("allowed_category",)
    search_fields = ("code", "allowed_category__name")
    autocomplete_fields = ("allowed_category",)
    readonly_fields = ("used_count", "created_at", "updated_at")
    date_hierarchy = "expires_at"
    inlines = (PromoCodeUsageInline,)

    @admin.display(description="Осталось применений")
    def remaining_uses(self, obj: PromoCode) -> int:
        return max(obj.max_uses - obj.used_count, 0)

    @admin.display(boolean=True, description="Доступен")
    def is_available(self, obj: PromoCode) -> bool:
        return (
            obj.is_active
            and obj.expires_at > timezone.now()
            and obj.used_count < obj.max_uses
        )


@admin.register(PromoCodeUsage)
class PromoCodeUsageAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Provide read-only access to the promo-code usage audit log."""

    list_display = ("id", "promo_code", "user", "order", "created_at")
    list_filter = ("promo_code", "created_at")
    list_select_related = ("promo_code", "user", "order")
    search_fields = (
        "promo_code__code",
        "user__username",
        "user__email",
        "order__id",
    )
    readonly_fields = ("promo_code", "user", "order", "created_at")
    date_hierarchy = "created_at"

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_delete_permission(
        self,
        request: HttpRequest,
        obj: PromoCodeUsage | None = None,
    ) -> bool:
        return False
