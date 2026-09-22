from typing import cast

from drf_spectacular.utils import (
    OpenApiExample,
    PolymorphicProxySerializer,
    extend_schema,
)
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from config.api.serializers import (
    ErrorResponseSerializer,
    ValidationErrorResponseSerializer,
)
from orders.serializers import (
    CreateOrderInputData,
    CreateOrderInputSerializer,
    OrderOutputSerializer,
)
from orders.services.create_order import CreateOrderService


class CreateOrderView(APIView):
    """Validate a create-order request and delegate it to the application service."""

    permission_classes = (AllowAny,)

    @extend_schema(
        operation_id="createOrder",
        summary="Создать заказ",
        description=(
            "Создаёт заказ для пользователя из переданных товаров и при наличии "
            "`promo_code` применяет процентную скидку.\n\n"
            "Промокод применяется, только если он существует и активен, не "
            "просрочен, не исчерпал общий лимит использований и ещё не "
            "применялся этим пользователем. Скидка начисляется по каждой позиции "
            "отдельно: товары, исключённые из акций, и товары вне разрешённой "
            'категории промокода получают `discount` равный `"0"`. Если ни '
            "одна позиция не подходит, заказ не создаётся.\n\n"
            "Денежные поля выражены в рублях, `discount` — строковый коэффициент "
            'скидки: `"0.1"` означает 10 %.'
        ),
        tags=["orders"],
        request=CreateOrderInputSerializer,
        responses={
            201: OrderOutputSerializer,
            400: PolymorphicProxySerializer(
                component_name="OrderErrorResponse",
                serializers=[
                    ErrorResponseSerializer,
                    ValidationErrorResponseSerializer,
                ],
                resource_type_field_name=None,
            ),
        },
        examples=[
            OpenApiExample(
                "Заказ с промокодом",
                value={
                    "user_id": 1,
                    "goods": [{"good_id": 1, "quantity": 2}],
                    "promo_code": "SUMMER2025",
                },
                request_only=True,
            ),
            OpenApiExample(
                "Заказ без промокода",
                value={
                    "user_id": 1,
                    "goods": [{"good_id": 1, "quantity": 2}],
                },
                request_only=True,
            ),
            OpenApiExample(
                "Созданный заказ",
                value={
                    "user_id": 1,
                    "order_id": 1,
                    "goods": [
                        {
                            "good_id": 1,
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
                response_only=True,
                status_codes=["201"],
            ),
            OpenApiExample(
                "Доменная ошибка",
                value={
                    "code": "promo_code_expired",
                    "detail": "Срок действия промокода истёк.",
                },
                response_only=True,
                status_codes=["400"],
            ),
            OpenApiExample(
                "Ошибка валидации",
                value={
                    "code": "invalid_request",
                    "detail": "Ошибка валидации запроса.",
                    "errors": {
                        "goods": {
                            "non_field_errors": [
                                {
                                    "message": (
                                        "Заказ должен содержать хотя бы один товар."
                                    ),
                                    "code": "empty",
                                }
                            ]
                        }
                    },
                },
                response_only=True,
                status_codes=["400"],
            ),
        ],
    )
    def post(self, request: Request) -> Response:
        input_serializer = CreateOrderInputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        order = CreateOrderService.execute(
            cast(CreateOrderInputData, input_serializer.validated_data)
        )
        output_serializer = OrderOutputSerializer(order)

        return Response(output_serializer.data, status=status.HTTP_201_CREATED)
