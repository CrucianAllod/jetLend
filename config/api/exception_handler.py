import logging
from collections.abc import Mapping
from typing import Any

from rest_framework.exceptions import APIException, ErrorDetail, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from orders.exceptions import OrderCreationError, OrderErrorCode

logger = logging.getLogger(__name__)


def _serialize_error_detail(value: object) -> object:
    if isinstance(value, ErrorDetail):
        return {
            "message": str(value),
            "code": value.code or "invalid",
        }
    if isinstance(value, Mapping):
        return {str(key): _serialize_error_detail(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize_error_detail(item) for item in value]
    return str(value)


def _extract_detail(data: object) -> str:
    if isinstance(data, Mapping) and "detail" in data:
        return str(data["detail"])
    return "Не удалось выполнить запрос."


def _fallback_code(status_code: int) -> str:
    return {
        400: "bad_request",
        401: "not_authenticated",
        403: "permission_denied",
        404: "not_found",
        405: "method_not_allowed",
        415: "unsupported_media_type",
        429: "throttled",
    }.get(status_code, "api_error")


def exception_handler(
    exc: Exception,
    context: dict[str, Any],
) -> Response | None:
    """Convert DRF and order-domain exceptions into the public error schema."""

    if isinstance(exc, OrderCreationError):
        logger.info(
            "Order creation rejected: code=%s detail=%s",
            exc.code.value,
            exc.detail,
        )
        return Response(
            {
                "code": exc.code.value,
                "detail": exc.detail,
            },
            status=400,
        )

    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    if isinstance(exc, ValidationError):
        logger.info(
            "Request validation failed: fields=%s",
            sorted(response.data) if isinstance(response.data, Mapping) else "-",
        )
        response.data = {
            "code": OrderErrorCode.INVALID_REQUEST.value,
            "detail": "Ошибка валидации запроса.",
            "errors": _serialize_error_detail(response.data),
        }
        return response

    if isinstance(exc, APIException):
        codes = exc.get_codes()
        code = codes if isinstance(codes, str) else exc.default_code
    else:
        code = _fallback_code(response.status_code)

    detail = _extract_detail(response.data)
    logger.warning(
        "API request failed: status=%s code=%s detail=%s",
        response.status_code,
        code,
        detail,
    )
    response.data = {
        "code": code,
        "detail": detail,
    }
    return response
