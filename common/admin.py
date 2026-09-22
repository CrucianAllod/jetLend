class MoneyDisplayMixin:
    """Provide reusable formatting for minor currency units in Django admin."""

    @staticmethod
    def _format_money(amount_minor: int) -> str:
        rubles, kopecks = divmod(amount_minor, 100)
        return f"{rubles}.{kopecks:02d} ₽"
