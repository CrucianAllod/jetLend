from enum import StrEnum


class OrderErrorCode(StrEnum):
    """List stable public error codes produced while creating an order."""

    INVALID_REQUEST = "invalid_request"
    USER_NOT_FOUND = "user_not_found"
    GOOD_UNAVAILABLE = "good_unavailable"
    PROMO_CODE_NOT_FOUND = "promo_code_not_found"
    PROMO_CODE_EXPIRED = "promo_code_expired"
    PROMO_CODE_USAGE_LIMIT_REACHED = "promo_code_usage_limit_reached"
    PROMO_CODE_ALREADY_USED = "promo_code_already_used"
    PROMO_CODE_NOT_APPLICABLE = "promo_code_not_applicable"


class OrderCreationError(Exception):
    """Report an expected business-rule failure from the order service."""

    def __init__(self, *, code: OrderErrorCode, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(detail)
