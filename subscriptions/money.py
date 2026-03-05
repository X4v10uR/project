from decimal import Decimal


WEEKS_PER_YEAR = Decimal("52")
MONTHS_PER_YEAR = Decimal("12")


def monthly_equivalent(amount, billing_cycle):
    value = Decimal(amount or 0)
    if billing_cycle == "weekly":
        return value * WEEKS_PER_YEAR / MONTHS_PER_YEAR
    if billing_cycle == "yearly":
        return value / MONTHS_PER_YEAR
    return value
