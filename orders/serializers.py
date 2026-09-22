from decimal import Decimal
from typing import NotRequired, TypedDict

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from orders.dto import OrderGoodResult, OrderResult


class OrderGoodInputData(TypedDict):
    """Describe validated input for one requested product."""

    good_id: int
    quantity: int


class CreateOrderInputData(TypedDict):
    """Describe the complete validated create-order request."""

    user_id: int
    goods: list[OrderGoodInputData]
    promo_code: NotRequired[str]


class OrderGoodInputSerializer(serializers.Serializer[OrderGoodInputData]):
    """Validate a product identifier and its requested quantity."""

    good_id = serializers.IntegerField(
        min_value=1,
        error_messages={
            "required": "Укажите идентификатор товара.",
            "invalid": "Идентификатор товара должен быть целым числом.",
            "min_value": "Идентификатор товара должен быть положительным.",
        },
    )
    quantity = serializers.IntegerField(
        min_value=1,
        error_messages={
            "required": "Укажите количество товара.",
            "invalid": "Количество должно быть целым числом.",
            "min_value": "Количество должно быть не меньше единицы.",
        },
    )


class CreateOrderInputSerializer(serializers.Serializer[CreateOrderInputData]):
    """Validate and normalize the create-order request body."""

    user_id = serializers.IntegerField(
        min_value=1,
        error_messages={
            "required": "Укажите идентификатор пользователя.",
            "invalid": "Идентификатор пользователя должен быть целым числом.",
            "min_value": "Идентификатор пользователя должен быть положительным.",
        },
    )
    goods = OrderGoodInputSerializer(
        many=True,
        allow_empty=False,
        error_messages={
            "required": "Добавьте товары в заказ.",
            "empty": "Заказ должен содержать хотя бы один товар.",
        },
    )
    promo_code = serializers.CharField(
        required=False,
        allow_blank=False,
        max_length=64,
        trim_whitespace=True,
    )

    def validate_goods(
        self,
        value: list[OrderGoodInputData],
    ) -> list[OrderGoodInputData]:
        good_ids = [item["good_id"] for item in value]
        if len(good_ids) != len(set(good_ids)):
            raise serializers.ValidationError(
                "Один товар нельзя передать в заказе несколько раз.",
                code="duplicate_good",
            )
        return value

    def validate_promo_code(self, value: str) -> str:
        return value.strip().upper()


@extend_schema_field(
    {
        "type": "number",
        "description": (
            "Сумма в рублях. Целое число, если копеек нет, иначе число с двумя "
            "знаками после запятой."
        ),
        "example": 180,
    }
)
class MinorMoneyField(serializers.Field[int, object, int | Decimal, object]):
    """Render an integer minor-unit amount as a JSON-compatible major amount."""

    def to_representation(self, value: int) -> int | Decimal:
        rubles, kopecks = divmod(value, 100)
        if kopecks == 0:
            return rubles
        return Decimal(value) / Decimal(100)


@extend_schema_field(
    {
        "type": "string",
        "pattern": r"^(0|1|0\.\d{1,2})$",
        "description": (
            'Коэффициент скидки строкой: "0.1" означает 10 %, '
            '"0" — скидка не применена.'
        ),
        "example": "0.1",
    }
)
class DiscountRateField(serializers.Field[int, object, str, object]):
    """Render an integer percentage as a normalized decimal-rate string."""

    def to_representation(self, value: int) -> str:
        rate = Decimal(value) / Decimal(100)
        return format(rate.normalize(), "f")


class OrderGoodOutputSerializer(serializers.Serializer[OrderGoodResult]):
    """Serialize one calculated product line using the public API contract."""

    good_id = serializers.IntegerField(read_only=True)
    quantity = serializers.IntegerField(read_only=True)
    price = MinorMoneyField(source="price_minor", read_only=True)
    discount = DiscountRateField(source="discount_percent", read_only=True)
    total = MinorMoneyField(source="total_minor", read_only=True)


class OrderOutputSerializer(serializers.Serializer[OrderResult]):
    """Serialize a created order using the public API contract."""

    user_id = serializers.IntegerField(read_only=True)
    order_id = serializers.IntegerField(read_only=True)
    goods = OrderGoodOutputSerializer(many=True, read_only=True)
    price = MinorMoneyField(source="price_minor", read_only=True)
    discount = DiscountRateField(source="discount_percent", read_only=True)
    total = MinorMoneyField(source="total_minor", read_only=True)
