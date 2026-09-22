from drf_spectacular.utils import inline_serializer
from rest_framework import serializers

from orders.exceptions import OrderErrorCode

# Коды, которые DRF формирует сам, без участия доменного слоя.
FRAMEWORK_ERROR_CODES = (
    "bad_request",
    "not_authenticated",
    "permission_denied",
    "not_found",
    "method_not_allowed",
    "unsupported_media_type",
    "throttled",
    "parse_error",
    "api_error",
)


class ErrorResponseSerializer(serializers.Serializer[dict[str, object]]):
    """Describe the body of a domain or framework error for the OpenAPI schema."""

    code = serializers.ChoiceField(
        choices=[*[code.value for code in OrderErrorCode], *FRAMEWORK_ERROR_CODES],
        help_text="Стабильный машиночитаемый код ошибки.",
    )
    detail = serializers.CharField(help_text="Человекочитаемое описание ошибки.")


class FieldErrorSerializer(serializers.Serializer[dict[str, object]]):
    """Describe one validation message attached to a request field."""

    message = serializers.CharField()
    code = serializers.CharField()


# Поле называется ``errors`` и совпадает с одноимённым свойством
# ``Serializer.errors``, поэтому класс собирается динамически.
ValidationErrorResponseSerializer = inline_serializer(
    name="ValidationErrorResponse",
    fields={
        "code": serializers.ChoiceField(
            choices=[OrderErrorCode.INVALID_REQUEST.value],
        ),
        "detail": serializers.CharField(),
        "errors": serializers.DictField(
            child=serializers.JSONField(),
            help_text=(
                "Ошибки по полям запроса. Значение — список сообщений либо "
                "вложенный объект той же структуры для составных полей, "
                "например goods."
            ),
        ),
    },
)
