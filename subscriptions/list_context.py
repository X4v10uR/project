from datetime import timedelta
from decimal import Decimal

from django.db.models import Count
from django.urls import reverse
from django.utils import timezone

from .color_utils import normalize_subscription_display_color
from .models import Subscription, Transaction
from .money import monthly_equivalent


SUBSCRIPTION_CARD_COLORS = [
    "#F9F871",
    "#7BCFC0",
    "#B5A5E7",
    "#AFC0DE",
    "#F4C3A8",
    "#9ED6EA",
    "#C3DDA6",
    "#E7B3C6",
    "#D8C6A5",
    "#C7BEEA",
]

CATEGORY_COLORS = {
    "streaming": "#B5A5E7",
    "music": "#7BCFC0",
    "video": "#F4C3A8",
    "software": "#AFC0DE",
    "utilities": "#9ED6EA",
    "cloud": "#C7BEEA",
    "gaming": "#E7B3C6",
    "productivity": "#C3DDA6",
    "education": "#F9F871",
    "news": "#D8C6A5",
    "fitness": "#F4C3A8",
}

ALLOWED_STATUS_FILTERS = {choice for choice, _ in Subscription.STATUS_CHOICES}
ALLOWED_BILLING_CYCLES = {choice for choice, _ in Subscription.BILLING_CYCLE_CHOICES}
ALLOWED_SHARED_FILTERS = {"", "true", "false"}
ALLOWED_SORT_FIELDS = {"cost", "renewal_date", "service_name"}


def _personal_subscription_queryset(request):
    return (
        Subscription.objects.filter(
            user=request.user,
            team__isnull=True,
        )
        .select_related("card")
        .annotate(participant_count=Count("participants"))
    )


def filter_personal_subscriptions(request):
    query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').strip().lower()
    cycle_filter = request.GET.get('cycle', '').strip().lower()
    shared_filter = request.GET.get('shared', '').strip().lower()
    due_within_raw = request.GET.get('due_within', '').strip()
    sort_by = request.GET.get('sort', 'renewal_date').strip()

    if status_filter not in ALLOWED_STATUS_FILTERS:
        status_filter = ''
    if cycle_filter not in ALLOWED_BILLING_CYCLES:
        cycle_filter = ''
    if shared_filter not in ALLOWED_SHARED_FILTERS:
        shared_filter = ''
    if sort_by not in ALLOWED_SORT_FIELDS:
        sort_by = 'renewal_date'

    subscriptions = _personal_subscription_queryset(request)

    if query:
        subscriptions = subscriptions.filter(service_name__icontains=query)
    if status_filter:
        subscriptions = subscriptions.filter(status=status_filter)
    if cycle_filter:
        subscriptions = subscriptions.filter(billing_cycle=cycle_filter)
    if shared_filter == 'true':
        subscriptions = subscriptions.filter(is_shared=True)
    if shared_filter == 'false':
        subscriptions = subscriptions.filter(is_shared=False)

    due_within_days = None
    due_within = ''
    if due_within_raw:
        try:
            parsed_due_within = int(due_within_raw)
            if 1 <= parsed_due_within <= 365:
                due_within_days = parsed_due_within
                due_within = str(parsed_due_within)
        except (TypeError, ValueError):
            due_within_days = None

    if due_within_days is not None:
        today = timezone.localdate()
        subscriptions = subscriptions.filter(
            renewal_date__range=[today, today + timedelta(days=due_within_days)]
        )

    subscriptions = subscriptions.order_by(sort_by)

    filters = {
        'query': query,
        'status_filter': status_filter,
        'cycle_filter': cycle_filter,
        'shared_filter': shared_filter,
        'due_within': due_within,
        'sort_by': sort_by,
    }
    return subscriptions, filters


def build_subscription_list_context(request):
    subscriptions, filters = filter_personal_subscriptions(request)
    subscriptions = list(subscriptions)
    base_subscriptions = list(_personal_subscription_queryset(request))
    _apply_subscription_card_metadata(subscriptions)
    drawer_payload = _build_subscription_drawer_data(subscriptions)
    stats = _calculate_subscription_stats(base_subscriptions)
    burn_metrics = _calculate_burn_rate_metrics(base_subscriptions)
    filters_active = bool(
        filters.get("query")
        or filters.get("status_filter")
        or filters.get("cycle_filter")
        or filters.get("shared_filter")
        or filters.get("due_within")
        or filters.get("sort_by") not in ("", "renewal_date")
    )
    return {
        'subscriptions': subscriptions,
        'subscriptions_total': len(base_subscriptions),
        'subscriptions_filtered_total': len(subscriptions),
        'subscriptions_stats': stats,
        'subscriptions_burn_metrics': burn_metrics,
        'subscription_drawer_data': drawer_payload,
        'filters_active': filters_active,
        **filters,
    }


def _hex_to_rgb(value):
    raw = (value or "").strip()
    if not raw.startswith("#"):
        return 0, 0, 0
    hex_value = raw.lstrip("#")
    if len(hex_value) == 3:
        hex_value = "".join(ch * 2 for ch in hex_value)
    if len(hex_value) != 6:
        return 0, 0, 0
    try:
        return (
            int(hex_value[0:2], 16),
            int(hex_value[2:4], 16),
            int(hex_value[4:6], 16),
        )
    except ValueError:
        return 0, 0, 0


def _is_dark_color(value):
    r, g, b = _hex_to_rgb(value)
    luminance = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
    return luminance < 0.6


def _apply_subscription_card_metadata(subscriptions):
    today = timezone.localdate()
    for index, subscription in enumerate(subscriptions):
        category_key = (subscription.category or "").strip().lower()
        color = normalize_subscription_display_color(getattr(subscription, "display_color", ""))
        if not color:
            color = CATEGORY_COLORS.get(category_key) or SUBSCRIPTION_CARD_COLORS[
                index % len(SUBSCRIPTION_CARD_COLORS)
            ]
        is_dark = _is_dark_color(color)
        subscription.card_color = color
        subscription.card_text_is_light = is_dark
        subscription.card_text_class = "text-white" if is_dark else "text-slate-900"
        subscription.card_muted_class = "text-white/65" if is_dark else "text-slate-600"
        subscription.card_divider_class = "border-white/15" if is_dark else "border-slate-200"
        subscription.card_badge_class = (
            "bg-white/15 text-white" if is_dark else "bg-slate-900/10 text-slate-700"
        )
        subscription.card_badge_border_class = "border-white/20" if is_dark else "border-slate-200"

        if subscription.renewal_date:
            subscription.days_until_renewal = (subscription.renewal_date - today).days
        else:
            subscription.days_until_renewal = None

        if subscription.days_until_renewal is None:
            subscription.renewal_text_class = subscription.card_muted_class
        elif subscription.days_until_renewal < 0:
            subscription.renewal_text_class = "text-red-300" if is_dark else "text-red-600"
        elif subscription.days_until_renewal <= 3:
            subscription.renewal_text_class = "text-yellow-300" if is_dark else "text-orange-600"
        else:
            subscription.renewal_text_class = subscription.card_text_class


def _normalize_currency_code(raw_currency):
    currency = (raw_currency or "USD").strip().upper()
    return currency or "USD"


def _format_currency_amount(amount, currency):
    if currency == "USD":
        return f"${amount:.2f}"
    return f"{currency} {amount:.2f}"


def _accumulate_monthly_spend_by_currency(subscriptions):
    totals = {}
    for subscription in subscriptions:
        currency = _normalize_currency_code(subscription.currency)
        totals[currency] = totals.get(currency, Decimal("0")) + monthly_equivalent(
            subscription.user_cost,
            subscription.billing_cycle,
        )
    return totals


def _format_spend_display(spend_by_currency):
    if not spend_by_currency:
        return "$0.00"
    if len(spend_by_currency) > 1:
        return "Multiple currencies"

    currency, amount = next(iter(spend_by_currency.items()))
    return _format_currency_amount(amount, currency)


def _calculate_subscription_stats(subscriptions):
    total = len(subscriptions)
    active = sum(1 for s in subscriptions if s.status == "active")
    paused = sum(1 for s in subscriptions if s.status == "paused")
    cancelled = sum(1 for s in subscriptions if s.status == "cancelled")
    active_subscriptions = [
        subscription for subscription in subscriptions if subscription.status == "active"
    ]
    spend_by_currency = _accumulate_monthly_spend_by_currency(active_subscriptions)
    is_mixed_currency = len(spend_by_currency) > 1

    if not spend_by_currency:
        monthly_spend = Decimal("0")
        monthly_spend_currency = "USD"
    elif is_mixed_currency:
        monthly_spend = None
        monthly_spend_currency = "MIXED"
    else:
        monthly_spend_currency, monthly_spend = next(iter(spend_by_currency.items()))

    return {
        "total": total,
        "active": active,
        "paused": paused,
        "cancelled": cancelled,
        "monthly_spend": monthly_spend,
        "monthly_spend_currency": monthly_spend_currency,
        "monthly_spend_display": _format_spend_display(spend_by_currency),
        "monthly_spend_is_mixed": is_mixed_currency,
    }


def _calculate_burn_rate_metrics(subscriptions):
    active_subscriptions = []
    tracked_subscriptions = []
    active_count = 0
    tracked_count = 0

    for subscription in subscriptions:
        if subscription.status == "cancelled":
            continue

        tracked_subscriptions.append(subscription)
        tracked_count += 1

        if subscription.status == "active":
            active_subscriptions.append(subscription)
            active_count += 1

    active_spend_by_currency = _accumulate_monthly_spend_by_currency(active_subscriptions)
    tracked_spend_by_currency = _accumulate_monthly_spend_by_currency(tracked_subscriptions)
    spend_is_mixed = len(tracked_spend_by_currency) > 1

    active_share_percent = 0
    share_basis = "count"
    active_monthly_spend = Decimal("0")
    tracked_monthly_spend = Decimal("0")
    active_monthly_spend_currency = "USD"
    tracked_monthly_spend_currency = "USD"

    if not spend_is_mixed and tracked_spend_by_currency:
        tracked_monthly_spend_currency, tracked_monthly_spend = next(
            iter(tracked_spend_by_currency.items())
        )
        active_monthly_spend_currency = tracked_monthly_spend_currency
        active_monthly_spend = active_spend_by_currency.get(
            tracked_monthly_spend_currency, Decimal("0")
        )
        if tracked_monthly_spend > 0:
            share_basis = "spend"
            active_share_percent = int(
                (active_monthly_spend * Decimal("100") / tracked_monthly_spend).quantize(
                    Decimal("1")
                )
            )

    if share_basis != "spend" and tracked_count > 0:
        active_share_percent = int(
            (Decimal(active_count) * Decimal("100") / Decimal(tracked_count)).quantize(
                Decimal("1")
            )
        )

    if spend_is_mixed:
        active_monthly_spend = None
        tracked_monthly_spend = None
        active_monthly_spend_currency = "MIXED"
        tracked_monthly_spend_currency = "MIXED"

    active_share_width = active_share_percent
    if active_share_percent > 0 and active_share_width < 12:
        active_share_width = 12

    return {
        "active_monthly_spend": active_monthly_spend,
        "tracked_monthly_spend": tracked_monthly_spend,
        "active_monthly_spend_currency": active_monthly_spend_currency,
        "tracked_monthly_spend_currency": tracked_monthly_spend_currency,
        "active_monthly_spend_display": _format_spend_display(active_spend_by_currency),
        "tracked_monthly_spend_display": _format_spend_display(tracked_spend_by_currency),
        "active_count": active_count,
        "tracked_count": tracked_count,
        "active_share_basis": share_basis,
        "spend_is_mixed": spend_is_mixed,
        "active_share_percent": max(0, min(active_share_percent, 100)),
        "active_share_width": max(0, min(active_share_width, 100)),
    }


def _ordinal_suffix(day):
    if 11 <= (day % 100) <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")


def _build_subscription_drawer_data(subscriptions):
    subscription_ids = [subscription.pk for subscription in subscriptions]
    transactions_by_subscription = {sub_id: [] for sub_id in subscription_ids}

    if subscription_ids:
        recent_transactions = (
            Transaction.objects.filter(
                subscription_id__in=subscription_ids,
                source=Transaction.SOURCE_RENEWAL,
            )
            .only("subscription_id", "charged_for_date", "amount", "currency", "charged_at")
            .order_by("subscription_id", "-charged_for_date", "-charged_at")
        )
        for transaction in recent_transactions:
            bucket = transactions_by_subscription.get(transaction.subscription_id)
            if bucket is None or len(bucket) >= 6:
                continue
            currency = _normalize_currency_code(transaction.currency)
            bucket.append(
                {
                    "charged_for_date": (
                        transaction.charged_for_date.isoformat()
                        if transaction.charged_for_date
                        else ""
                    ),
                    "charged_for_date_display": (
                        transaction.charged_for_date.strftime("%b %d, %Y")
                        if transaction.charged_for_date
                        else "Unknown date"
                    ),
                    "amount": str(transaction.amount),
                    "currency": currency,
                    "amount_display": _format_currency_amount(transaction.amount, currency),
                }
            )

    payload = {}
    for subscription in subscriptions:
        currency = _normalize_currency_code(subscription.currency)
        total_cost = subscription.cost or Decimal("0")
        user_cost = subscription.user_cost or Decimal("0")
        participant_count = int(getattr(subscription, "participant_count", 0) or 0)
        total_people = 1 + participant_count if subscription.is_shared else 1

        share_percent = 0
        if total_cost > 0:
            share_percent = int(
                (user_cost * Decimal("100") / total_cost).quantize(Decimal("1"))
            )
        share_percent = max(0, min(share_percent, 100))

        renewal_date_display = (
            subscription.renewal_date.strftime("%b %d, %Y")
            if subscription.renewal_date
            else "No renewal date"
        )
        billing_cycle_display = subscription.get_billing_cycle_display()
        if subscription.renewal_date:
            renewal_day = subscription.renewal_date.day
            billing_cycle_detail = (
                f"{billing_cycle_display}, {renewal_day}{_ordinal_suffix(renewal_day)}"
            )
        else:
            billing_cycle_detail = billing_cycle_display

        card_last4 = subscription.card.last4 if subscription.card else ""
        card_brand = (subscription.card.brand or "").upper() if subscription.card else ""
        icon_url = subscription.get_icon_url()
        fallback_icon = subscription.get_fallback_icon()

        payload[str(subscription.pk)] = {
            "id": subscription.pk,
            "service_name": subscription.service_name,
            "plan_name": subscription.plan_name or "",
            "category": subscription.category or "Uncategorized",
            "billing_cycle": subscription.billing_cycle,
            "billing_cycle_display": billing_cycle_display,
            "billing_cycle_detail": billing_cycle_detail,
            "status": subscription.status,
            "status_display": subscription.get_status_display(),
            "currency": currency,
            "cost": str(total_cost),
            "cost_display": _format_currency_amount(total_cost, currency),
            "user_cost": str(user_cost),
            "user_cost_display": _format_currency_amount(user_cost, currency),
            "is_shared": bool(subscription.is_shared),
            "participant_count": participant_count,
            "total_people": total_people,
            "share_percent": share_percent,
            "renewal_date": (
                subscription.renewal_date.isoformat()
                if subscription.renewal_date
                else ""
            ),
            "renewal_date_display": renewal_date_display,
            "days_until_renewal": subscription.days_until_renewal,
            "account_email": subscription.account_email or "",
            "has_card": bool(subscription.card_id),
            "card_last4": card_last4,
            "card_brand": card_brand,
            "icon_url": icon_url,
            "fallback_icon": fallback_icon,
            "history": transactions_by_subscription.get(subscription.pk, []),
            "edit_url": reverse("subscriptions:update", args=[subscription.pk]),
            "delete_url": reverse("subscriptions:delete", args=[subscription.pk]),
            "status_url": reverse("subscriptions:update_status", args=[subscription.pk]),
        }

    return payload
