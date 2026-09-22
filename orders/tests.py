from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from threading import Barrier
from typing import Any, cast

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import close_old_connections
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ErrorDetail, ValidationError
from rest_framework.test import APITestCase

from catalog.models import Category, Product
from config.api.exception_handler import exception_handler
from orders.dto import OrderGoodResult, OrderResult
from orders.exceptions import OrderCreationError, OrderErrorCode
from orders.models import Order, OrderItem
from orders.serializers import (
    CreateOrderInputData,
    CreateOrderInputSerializer,
    OrderOutputSerializer,
)
from orders.services.create_order import CreateOrderService
from orders.services.discount_calculator import (
    DiscountCalculator,
    DiscountLineInput,
)
from promocodes.models import PromoCode, PromoCodeUsage


class CreateOrderServiceTests(TestCase):
    def setUp(self) -> None:
        self.user = get_user_model()._default_manager.create(username="customer")
        self.category = Category.objects.create(name="Books", slug="books")
        self.other_category = Category.objects.create(
            name="Games",
            slug="games",
        )
        self.product = Product.objects.create(
            name="Book",
            category=self.category,
            price_minor=10_000,
        )
        self.other_product = Product.objects.create(
            name="Game",
            category=self.other_category,
            price_minor=5_000,
        )

    def _promo_code(self, **overrides: Any) -> PromoCode:
        values: dict[str, Any] = {
            "code": "SUMMER2025",
            "discount_percent": 10,
            "expires_at": timezone.now() + timedelta(days=1),
            "max_uses": 10,
        }
        values.update(overrides)
        return PromoCode.objects.create(**values)

    def test_creates_order_without_promo_code(self) -> None:
        data: CreateOrderInputData = {
            "user_id": self.user.pk,
            "goods": [{"good_id": self.product.pk, "quantity": 2}],
        }

        result = CreateOrderService.execute(data)

        order = Order.objects.get(pk=result.order_id)
        item = OrderItem.objects.get(order=order)
        self.assertEqual(order.subtotal_minor, 20_000)
        self.assertEqual(order.discount_minor, 0)
        self.assertEqual(order.total_minor, 20_000)
        self.assertEqual(item.product_name, "Book")
        self.assertEqual(item.unit_price_minor, 10_000)
        self.assertEqual(result.discount_percent, 0)

    def test_applies_promo_only_to_allowed_category(self) -> None:
        promo_code = self._promo_code(allowed_category=self.category)
        data: CreateOrderInputData = {
            "user_id": self.user.pk,
            "goods": [
                {"good_id": self.product.pk, "quantity": 2},
                {"good_id": self.other_product.pk, "quantity": 1},
            ],
            "promo_code": promo_code.code,
        }

        result = CreateOrderService.execute(data)

        promo_code.refresh_from_db()
        self.assertEqual(result.price_minor, 25_000)
        self.assertEqual(result.total_minor, 23_000)
        self.assertEqual(
            [good.discount_percent for good in result.goods],
            [10, 0],
        )
        self.assertEqual(promo_code.used_count, 1)
        self.assertTrue(
            PromoCodeUsage.objects.filter(
                promo_code=promo_code,
                user=self.user,
                order_id=result.order_id,
            ).exists()
        )

    def test_rejects_missing_user_without_creating_order(self) -> None:
        data: CreateOrderInputData = {
            "user_id": 999_999,
            "goods": [{"good_id": self.product.pk, "quantity": 1}],
        }

        with self.assertRaises(OrderCreationError) as error:
            CreateOrderService.execute(data)

        self.assertEqual(error.exception.code, OrderErrorCode.USER_NOT_FOUND)
        self.assertFalse(Order.objects.exists())

    def test_rejects_inactive_product(self) -> None:
        self.product.is_active = False
        self.product.save(update_fields=("is_active",))
        data: CreateOrderInputData = {
            "user_id": self.user.pk,
            "goods": [{"good_id": self.product.pk, "quantity": 1}],
        }

        with self.assertRaises(OrderCreationError) as error:
            CreateOrderService.execute(data)

        self.assertEqual(error.exception.code, OrderErrorCode.GOOD_UNAVAILABLE)

    def test_rejects_expired_promo_code(self) -> None:
        promo_code = self._promo_code(expires_at=timezone.now() - timedelta(seconds=1))
        data: CreateOrderInputData = {
            "user_id": self.user.pk,
            "goods": [{"good_id": self.product.pk, "quantity": 1}],
            "promo_code": promo_code.code,
        }

        with self.assertRaises(OrderCreationError) as error:
            CreateOrderService.execute(data)

        self.assertEqual(error.exception.code, OrderErrorCode.PROMO_CODE_EXPIRED)
        self.assertFalse(Order.objects.exists())

    def test_rejects_promo_without_eligible_goods(self) -> None:
        promo_code = self._promo_code(allowed_category=self.other_category)
        data: CreateOrderInputData = {
            "user_id": self.user.pk,
            "goods": [{"good_id": self.product.pk, "quantity": 1}],
            "promo_code": promo_code.code,
        }

        with self.assertRaises(OrderCreationError) as error:
            CreateOrderService.execute(data)

        self.assertEqual(error.exception.code, OrderErrorCode.PROMO_CODE_NOT_APPLICABLE)
        self.assertFalse(Order.objects.exists())
        self.assertFalse(PromoCodeUsage.objects.exists())

    def test_rejects_unknown_promo_code(self) -> None:
        data: CreateOrderInputData = {
            "user_id": self.user.pk,
            "goods": [{"good_id": self.product.pk, "quantity": 1}],
            "promo_code": "MISSING",
        }

        with self.assertRaises(OrderCreationError) as error:
            CreateOrderService.execute(data)

        self.assertEqual(error.exception.code, OrderErrorCode.PROMO_CODE_NOT_FOUND)
        self.assertFalse(Order.objects.exists())

    def test_rejects_inactive_promo_code(self) -> None:
        promo_code = self._promo_code(is_active=False)
        data: CreateOrderInputData = {
            "user_id": self.user.pk,
            "goods": [{"good_id": self.product.pk, "quantity": 1}],
            "promo_code": promo_code.code,
        }

        with self.assertRaises(OrderCreationError) as error:
            CreateOrderService.execute(data)

        self.assertEqual(error.exception.code, OrderErrorCode.PROMO_CODE_NOT_FOUND)
        self.assertFalse(Order.objects.exists())

    def test_rejects_exhausted_promo_code(self) -> None:
        promo_code = self._promo_code(max_uses=1, used_count=1)
        data: CreateOrderInputData = {
            "user_id": self.user.pk,
            "goods": [{"good_id": self.product.pk, "quantity": 1}],
            "promo_code": promo_code.code,
        }

        with self.assertRaises(OrderCreationError) as error:
            CreateOrderService.execute(data)

        promo_code.refresh_from_db()
        self.assertEqual(
            error.exception.code,
            OrderErrorCode.PROMO_CODE_USAGE_LIMIT_REACHED,
        )
        self.assertEqual(promo_code.used_count, 1)
        self.assertFalse(Order.objects.exists())

    def test_rejects_missing_product(self) -> None:
        data: CreateOrderInputData = {
            "user_id": self.user.pk,
            "goods": [
                {"good_id": self.product.pk, "quantity": 1},
                {"good_id": 999_999, "quantity": 1},
            ],
        }

        with self.assertRaises(OrderCreationError) as error:
            CreateOrderService.execute(data)

        self.assertEqual(error.exception.code, OrderErrorCode.GOOD_UNAVAILABLE)
        self.assertFalse(Order.objects.exists())

    def test_rejects_second_use_and_rolls_back(self) -> None:
        promo_code = self._promo_code()
        data: CreateOrderInputData = {
            "user_id": self.user.pk,
            "goods": [{"good_id": self.product.pk, "quantity": 1}],
            "promo_code": promo_code.code,
        }
        CreateOrderService.execute(data)

        with self.assertRaises(OrderCreationError) as error:
            CreateOrderService.execute(data)

        promo_code.refresh_from_db()
        self.assertEqual(error.exception.code, OrderErrorCode.PROMO_CODE_ALREADY_USED)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(PromoCodeUsage.objects.count(), 1)
        self.assertEqual(promo_code.used_count, 1)


class CreateOrderConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self) -> None:
        user_model = get_user_model()
        self.first_user = user_model._default_manager.create(username="first")
        self.second_user = user_model._default_manager.create(username="second")
        category = Category.objects.create(name="Books", slug="books")
        self.first_product = Product.objects.create(
            name="First book",
            category=category,
            price_minor=1_000,
        )
        self.second_product = Product.objects.create(
            name="Second book",
            category=category,
            price_minor=1_000,
        )
        self.promo_code = PromoCode.objects.create(
            code="LAST",
            discount_percent=10,
            expires_at=timezone.now() + timedelta(days=1),
            max_uses=1,
        )

    def _create_order(
        self,
        *,
        user_id: int,
        good_id: int,
        barrier: Barrier,
    ) -> str:
        close_old_connections()
        barrier.wait()
        data: CreateOrderInputData = {
            "user_id": user_id,
            "goods": [{"good_id": good_id, "quantity": 1}],
            "promo_code": self.promo_code.code,
        }
        try:
            CreateOrderService.execute(data)
        except OrderCreationError as error:
            return error.code.value
        finally:
            close_old_connections()
        return "success"

    def test_last_promo_use_is_not_oversubscribed(self) -> None:
        barrier = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = (
                executor.submit(
                    self._create_order,
                    user_id=self.first_user.pk,
                    good_id=self.first_product.pk,
                    barrier=barrier,
                ),
                executor.submit(
                    self._create_order,
                    user_id=self.second_user.pk,
                    good_id=self.second_product.pk,
                    barrier=barrier,
                ),
            )
            results = sorted(future.result() for future in futures)

        self.promo_code.refresh_from_db()
        self.assertEqual(results, ["promo_code_usage_limit_reached", "success"])
        self.assertEqual(self.promo_code.used_count, 1)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(PromoCodeUsage.objects.count(), 1)


class CreateOrderAPITests(APITestCase):
    def setUp(self) -> None:
        self.url = reverse("orders:create")
        self.user = get_user_model()._default_manager.create(username="api-user")
        self.category = Category.objects.create(name="Books", slug="api-books")
        self.product = Product.objects.create(
            name="Book",
            category=self.category,
            price_minor=10_000,
        )

    def test_creates_order(self) -> None:
        response = self.client.post(
            self.url,
            {
                "user_id": self.user.pk,
                "goods": [{"good_id": self.product.pk, "quantity": 2}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = Order.objects.get()
        self.assertEqual(
            response.json(),
            {
                "user_id": self.user.pk,
                "order_id": order.pk,
                "goods": [
                    {
                        "good_id": self.product.pk,
                        "quantity": 2,
                        "price": 100,
                        "discount": "0",
                        "total": 200,
                    }
                ],
                "price": 200,
                "discount": "0",
                "total": 200,
            },
        )

    def test_creates_order_with_promo_code(self) -> None:
        PromoCode.objects.create(
            code="SUMMER2025",
            discount_percent=10,
            expires_at=timezone.now() + timedelta(days=1),
            max_uses=10,
        )

        response = self.client.post(
            self.url,
            {
                "user_id": self.user.pk,
                "goods": [{"good_id": self.product.pk, "quantity": 2}],
                "promo_code": " summer2025 ",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()["discount"], "0.1")
        self.assertEqual(response.json()["total"], 180)

    def test_returns_structured_validation_error(self) -> None:
        response = self.client.post(
            self.url,
            {"user_id": self.user.pk, "goods": []},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data = response.json()
        self.assertEqual(data["code"], "invalid_request")
        self.assertEqual(
            data["errors"]["goods"]["non_field_errors"][0]["code"],
            "empty",
        )

    def test_returns_structured_domain_error(self) -> None:
        response = self.client.post(
            self.url,
            {
                "user_id": 999_999,
                "goods": [{"good_id": self.product.pk, "quantity": 1}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json()["code"], "user_not_found")
        self.assertFalse(Order.objects.exists())

    def test_rejects_unsupported_method(self) -> None:
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(response.json()["code"], "method_not_allowed")


class SeedDemoCommandTests(TestCase):
    def test_creates_demo_data_and_is_idempotent(self) -> None:
        output = StringIO()

        call_command("seed_demo", stdout=output)
        call_command("seed_demo", stdout=output)

        user = get_user_model()._default_manager.get(username="demo_customer")
        promo_code = PromoCode.objects.get(code="SUMMER2025")
        self.assertEqual(
            Category.objects.filter(slug__in=("demo-books", "demo-games")).count(),
            2,
        )
        self.assertEqual(Product.objects.filter(name__startswith="Demo ").count(), 3)
        self.assertEqual(PromoCode.objects.filter(code="SUMMER2025").count(), 1)
        self.assertEqual(promo_code.discount_percent, 10)
        allowed_category = promo_code.allowed_category
        self.assertIsNotNone(allowed_category)
        assert allowed_category is not None
        self.assertEqual(allowed_category.slug, "demo-books")
        self.assertIn(f'"user_id": {user.pk}', output.getvalue())
        self.assertIn('"promo_code": "SUMMER2025"', output.getvalue())


class DiscountCalculatorTests(SimpleTestCase):
    @staticmethod
    def _line(
        *,
        good_id: int = 1,
        price_minor: int = 10_000,
        quantity: int = 2,
        category_id: int = 10,
        is_discount_excluded: bool = False,
    ) -> DiscountLineInput:
        return DiscountLineInput(
            good_id=good_id,
            unit_price_minor=price_minor,
            quantity=quantity,
            category_id=category_id,
            is_discount_excluded=is_discount_excluded,
        )

    def test_calculates_discount_for_all_goods(self) -> None:
        result = DiscountCalculator.calculate(
            [self._line()],
            discount_percent=10,
        )

        self.assertEqual(result.subtotal_minor, 20_000)
        self.assertEqual(result.discount_minor, 2_000)
        self.assertEqual(result.total_minor, 18_000)
        self.assertEqual(result.eligible_goods_count, 1)
        self.assertEqual(result.lines[0].discount_percent, 10)

    def test_calculates_order_without_promo_code(self) -> None:
        result = DiscountCalculator.calculate([self._line()])

        self.assertEqual(result.subtotal_minor, 20_000)
        self.assertEqual(result.discount_minor, 0)
        self.assertEqual(result.total_minor, 20_000)
        self.assertFalse(result.has_eligible_goods)

    def test_does_not_discount_excluded_good(self) -> None:
        result = DiscountCalculator.calculate(
            [self._line(is_discount_excluded=True)],
            discount_percent=25,
        )

        self.assertEqual(result.discount_minor, 0)
        self.assertEqual(result.lines[0].discount_percent, 0)
        self.assertFalse(result.has_eligible_goods)

    def test_discount_applies_only_to_matching_category(self) -> None:
        result = DiscountCalculator.calculate(
            [
                self._line(good_id=1, category_id=10),
                self._line(good_id=2, category_id=20),
            ],
            discount_percent=10,
            allowed_category_id=10,
        )

        self.assertEqual(result.subtotal_minor, 40_000)
        self.assertEqual(result.discount_minor, 2_000)
        self.assertEqual(result.total_minor, 38_000)
        self.assertEqual(result.eligible_goods_count, 1)
        self.assertEqual(
            [line.discount_percent for line in result.lines],
            [10, 0],
        )

    def test_rounds_half_kopeck_up(self) -> None:
        result = DiscountCalculator.calculate(
            [self._line(price_minor=50, quantity=1)],
            discount_percent=1,
        )

        self.assertEqual(result.discount_minor, 1)
        self.assertEqual(result.total_minor, 49)

    def test_zero_price_good_is_still_eligible(self) -> None:
        result = DiscountCalculator.calculate(
            [self._line(price_minor=0, quantity=1)],
            discount_percent=10,
        )

        self.assertTrue(result.has_eligible_goods)
        self.assertEqual(result.discount_minor, 0)
        self.assertEqual(result.lines[0].discount_percent, 10)

    def test_rejects_invalid_discount_percent(self) -> None:
        for discount_percent in (-1, 101):
            with (
                self.subTest(discount_percent=discount_percent),
                self.assertRaisesRegex(ValueError, "between 0 and 100"),
            ):
                DiscountCalculator.calculate(
                    [self._line()],
                    discount_percent=discount_percent,
                )

    def test_rejects_empty_order(self) -> None:
        with self.assertRaisesRegex(ValueError, "At least one"):
            DiscountCalculator.calculate([], discount_percent=10)

    def test_rejects_non_positive_quantity(self) -> None:
        with self.assertRaisesRegex(ValueError, "Quantity"):
            DiscountCalculator.calculate(
                [self._line(quantity=0)],
                discount_percent=10,
            )

    def test_rejects_negative_price(self) -> None:
        with self.assertRaisesRegex(ValueError, "price"):
            DiscountCalculator.calculate(
                [self._line(price_minor=-1)],
                discount_percent=10,
            )


class CreateOrderInputSerializerTests(SimpleTestCase):
    def test_accepts_request_without_promo_code(self) -> None:
        serializer = CreateOrderInputSerializer(
            data={
                "user_id": 1,
                "goods": [{"good_id": 10, "quantity": 2}],
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertNotIn("promo_code", serializer.validated_data)

    def test_normalizes_promo_code(self) -> None:
        serializer = CreateOrderInputSerializer(
            data={
                "user_id": 1,
                "goods": [{"good_id": 10, "quantity": 2}],
                "promo_code": " summer2025 ",
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["promo_code"], "SUMMER2025")

    def test_rejects_duplicate_goods(self) -> None:
        serializer = CreateOrderInputSerializer(
            data={
                "user_id": 1,
                "goods": [
                    {"good_id": 10, "quantity": 1},
                    {"good_id": 10, "quantity": 2},
                ],
            }
        )

        self.assertFalse(serializer.is_valid())
        error = serializer.errors["goods"][0]
        self.assertEqual(error.code, "duplicate_good")

    def test_rejects_empty_order(self) -> None:
        serializer = CreateOrderInputSerializer(data={"user_id": 1, "goods": []})

        self.assertFalse(serializer.is_valid())
        error = serializer.errors["goods"]["non_field_errors"][0]
        self.assertEqual(error.code, "empty")


class OrderOutputSerializerTests(SimpleTestCase):
    def test_serializes_response_contract(self) -> None:
        result = OrderResult(
            user_id=1,
            order_id=7,
            goods=(
                OrderGoodResult(
                    good_id=10,
                    quantity=2,
                    price_minor=10_000,
                    discount_percent=10,
                    total_minor=18_000,
                ),
            ),
            price_minor=20_000,
            discount_percent=10,
            total_minor=18_000,
        )

        self.assertEqual(
            OrderOutputSerializer(result).data,
            {
                "user_id": 1,
                "order_id": 7,
                "goods": [
                    {
                        "good_id": 10,
                        "quantity": 2,
                        "price": 100,
                        "discount": "0.1",
                        "total": 180,
                    }
                ],
                "price": 200,
                "discount": "0.1",
                "total": 180,
            },
        )

    def test_preserves_kopecks_without_float(self) -> None:
        result = OrderResult(
            user_id=1,
            order_id=7,
            goods=(),
            price_minor=10_005,
            discount_percent=0,
            total_minor=10_005,
        )

        data = OrderOutputSerializer(result).data

        self.assertEqual(data["price"], Decimal("100.05"))
        self.assertEqual(data["discount"], "0")


class ExceptionHandlerTests(SimpleTestCase):
    def test_formats_validation_error(self) -> None:
        error = ValidationError(
            {"goods": [ErrorDetail("Invalid goods.", code="invalid_goods")]}
        )

        response = exception_handler(error, {})

        self.assertIsNotNone(response)
        assert response is not None
        data = cast(dict[str, Any], response.data)
        self.assertEqual(data["code"], "invalid_request")
        self.assertEqual(
            data["errors"],
            {
                "goods": [
                    {
                        "message": "Invalid goods.",
                        "code": "invalid_goods",
                    }
                ]
            },
        )

    def test_formats_domain_error(self) -> None:
        error = OrderCreationError(
            code=OrderErrorCode.PROMO_CODE_EXPIRED,
            detail="Promo code expired.",
        )

        response = exception_handler(error, {})

        self.assertIsNotNone(response)
        assert response is not None
        data = cast(dict[str, Any], response.data)
        self.assertEqual(
            data,
            {
                "code": "promo_code_expired",
                "detail": "Promo code expired.",
            },
        )


class OrderLoggingTests(APITestCase):
    def setUp(self) -> None:
        self.url = reverse("orders:create")
        self.user = get_user_model()._default_manager.create(username="log-user")
        category = Category.objects.create(name="Books", slug="log-books")
        self.product = Product.objects.create(
            name="Book",
            category=category,
            price_minor=10_000,
        )

    def test_logs_created_order(self) -> None:
        with self.assertLogs("orders.services.create_order", level="INFO") as logs:
            response = self.client.post(
                self.url,
                {
                    "user_id": self.user.pk,
                    "goods": [{"good_id": self.product.pk, "quantity": 1}],
                },
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(logs.records), 1)
        self.assertIn(f"order_id={response.json()['order_id']}", logs.output[0])
        self.assertIn(f"user_id={self.user.pk}", logs.output[0])
        self.assertIn("promo_code=None", logs.output[0])

    def test_logs_rejected_order(self) -> None:
        with self.assertLogs("config.api.exception_handler", level="INFO") as logs:
            response = self.client.post(
                self.url,
                {
                    "user_id": self.user.pk,
                    "goods": [{"good_id": self.product.pk, "quantity": 1}],
                    "promo_code": "MISSING",
                },
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(len(logs.records), 1)
        self.assertEqual(logs.records[0].levelname, "INFO")
        self.assertIn("code=promo_code_not_found", logs.output[0])

    def test_logs_validation_failure(self) -> None:
        with self.assertLogs("config.api.exception_handler", level="INFO") as logs:
            response = self.client.post(self.url, {"goods": []}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fields=['goods', 'user_id']", logs.output[0])


class OpenAPISchemaTests(APITestCase):
    def test_schema_describes_create_order(self) -> None:
        response = self.client.get(reverse("schema"), HTTP_ACCEPT="application/json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        schema = response.json()
        operation = schema["paths"]["/api/orders/"]["post"]
        self.assertEqual(operation["operationId"], "createOrder")
        self.assertIn("201", operation["responses"])
        self.assertIn("400", operation["responses"])

        good = schema["components"]["schemas"]["OrderGoodOutput"]["properties"]
        self.assertEqual(good["price"]["type"], "number")
        self.assertEqual(good["discount"]["type"], "string")

        request_body = schema["components"]["schemas"]["CreateOrderInputRequest"]
        self.assertEqual(sorted(request_body["required"]), ["goods", "user_id"])
        self.assertIn("promo_code", request_body["properties"])

    def test_swagger_ui_is_served(self) -> None:
        response = self.client.get(reverse("swagger-ui"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "swagger-ui")

    def test_redoc_is_served(self) -> None:
        response = self.client.get(reverse("redoc"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "redoc")
