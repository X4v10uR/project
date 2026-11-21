from decimal import Decimal


WEEKS_PER_YEAR = Decimal("52")
MONTHS_PER_YEAR = Decimal("12")


def equal_share(total, people, position):
    """Split whole cents in order, with the payer at position zero."""
    cents, remainder = divmod(int(total * 100), people)
    return Decimal(cents + (position < remainder)).scaleb(-2)


def monthly_equivalent(amount, billing_cycle):
    value = Decimal(amount or 0)
    if billing_cycle == "weekly":
        return value * WEEKS_PER_YEAR / MONTHS_PER_YEAR
    if billing_cycle == "quarterly":
        return value / 3
    if billing_cycle == "halfyearly":
        return value / 6
    if billing_cycle == "fourweekly":
        return value * Decimal('365.25') / 28 / MONTHS_PER_YEAR
    if billing_cycle == "yearly":
        return value / MONTHS_PER_YEAR
    return value
