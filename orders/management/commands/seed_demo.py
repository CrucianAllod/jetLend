import json
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from catalog.models import Category, Product
from promocodes.models import PromoCode

if TYPE_CHECKING:
    from django.contrib.auth.models import User


class Command(BaseCommand):
    """Seed repeatable catalog and promo data for a local API smoke test."""

    help = "Create or update data for a local API smoke test."

    def handle(self, *args: Any, **options: Any) -> None:
        with transaction.atomic():
            user = self._create_user()
            books, games = self._create_categories()
            book, game, gift_card = self._create_products(books=books, games=games)
            promo_code = self._create_promo_code(allowed_category=books)

        request_body = {
            "user_id": user.pk,
            "goods": [
                {"good_id": book.pk, "quantity": 2},
                {"good_id": game.pk, "quantity": 1},
                {"good_id": gift_card.pk, "quantity": 1},
            ],
            "promo_code": promo_code.code,
        }
        self.stdout.write(self.style.SUCCESS("Demo data is ready."))
        self.stdout.write("POST http://127.0.0.1:8000/api/orders/")
        self.stdout.write(json.dumps(request_body, ensure_ascii=False, indent=2))

    @staticmethod
    def _create_user() -> User:
        user, created = get_user_model()._default_manager.get_or_create(
            username="demo_customer",
            defaults={"email": "demo@example.com"},
        )
        if created:
            user.set_unusable_password()
            user.save(update_fields=("password",))
        return user

    @staticmethod
    def _create_categories() -> tuple[Category, Category]:
        books, _ = Category.objects.update_or_create(
            slug="demo-books",
            defaults={"name": "Demo books"},
        )
        games, _ = Category.objects.update_or_create(
            slug="demo-games",
            defaults={"name": "Demo games"},
        )
        return books, games

    @staticmethod
    def _create_products(
        *,
        books: Category,
        games: Category,
    ) -> tuple[Product, Product, Product]:
        book, _ = Product.objects.update_or_create(
            name="Demo Django book",
            defaults={
                "category": books,
                "price_minor": 10_000,
                "is_active": True,
                "is_discount_excluded": False,
            },
        )
        game, _ = Product.objects.update_or_create(
            name="Demo board game",
            defaults={
                "category": games,
                "price_minor": 5_000,
                "is_active": True,
                "is_discount_excluded": False,
            },
        )
        gift_card, _ = Product.objects.update_or_create(
            name="Demo gift card",
            defaults={
                "category": books,
                "price_minor": 2_500,
                "is_active": True,
                "is_discount_excluded": True,
            },
        )
        return book, game, gift_card

    @staticmethod
    def _create_promo_code(*, allowed_category: Category) -> PromoCode:
        promo_code = PromoCode.objects.filter(code__iexact="SUMMER2025").first()
        if promo_code is None:
            return PromoCode.objects.create(
                code="SUMMER2025",
                discount_percent=10,
                expires_at=timezone.now() + timedelta(days=30),
                max_uses=100,
                allowed_category=allowed_category,
            )

        promo_code.code = "SUMMER2025"
        promo_code.discount_percent = 10
        promo_code.expires_at = timezone.now() + timedelta(days=30)
        promo_code.max_uses = max(promo_code.used_count, 100)
        promo_code.allowed_category = allowed_category
        promo_code.is_active = True
        promo_code.save(
            update_fields=(
                "code",
                "discount_percent",
                "expires_at",
                "max_uses",
                "allowed_category",
                "is_active",
                "updated_at",
            )
        )
        return promo_code
