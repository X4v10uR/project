from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlencode

from django.urls import reverse
from django.utils import timezone

from subscriptions.models import Subscription, Transaction
from subscriptions.services import refresh_subscription_renewal_date

from .constants import (
    CARD_THEME_BY_SERVICE,
    CARD_THEME_ROTATION,
    PLACEHOLDER_ACTIVE,
    PLACEHOLDER_SUBSCRIPTION,
    PLACEHOLDER_TRANSACTION,
    PLACEHOLDER_UPCOMING,
)


def _quantize_money(value):
    return value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _money_symbol(currency_code):
    return {
        'USD': '$',
        'EUR': 'EUR ',
        'GBP': 'GBP ',
        'INR': 'INR ',
    }.get((currency_code or '').upper(), f"{currency_code or 'USD'} ")


def _format_money(amount, currency='USD'):
    symbol = _money_symbol(currency)
    return f"{symbol}{_quantize_money(amount)}"


def _format_currency_breakdown(totals):
    if not totals:
        return _format_money(Decimal('0.00'), 'USD')

    ordered = sorted(totals.items(), key=lambda item: item[0])
    parts = [_format_money(amount, currency) for currency, amount in ordered]
    return ' + '.join(parts)


def _monthly_cost(subscription):
    cost = subscription.user_cost if subscription.is_shared else subscription.cost
    if subscription.billing_cycle == 'weekly':
        return cost * Decimal('4')
    if subscription.billing_cycle == 'yearly':
        return cost / Decimal('12')
    return cost


def _days_left_text(renewal_date, today):
    if not renewal_date:
        return 'No due date'
    days = (renewal_date - today).days
    if days < 0:
        overdue_days = abs(days)
        if overdue_days == 1:
            return '1 day overdue'
        return f'{overdue_days} days overdue'
    if days == 0:
        return 'Due today'
    if days == 1:
        return '1 day left'
    return f'{days} days left'


def _service_theme(service_name, index):
    normalized = (service_name or '').strip().lower()
    if normalized in CARD_THEME_BY_SERVICE:
        return CARD_THEME_BY_SERVICE[normalized]
    return CARD_THEME_ROTATION[index % len(CARD_THEME_ROTATION)]


def _greeting_name(email):
    local_part = (email or 'User').split('@')[0]
    safe_name = local_part.replace('.', ' ').replace('_', ' ').strip()
    if not safe_name:
        return 'User'
    return safe_name.title()


def _slot_pad(items, total_slots, placeholder_builder):
    padded = list(items[:total_slots])
    while len(padded) < total_slots:
        padded.append(placeholder_builder(len(padded)))
    return padded


def _renewal_view_all_url():
    base = reverse('subscriptions:list')
    query = urlencode({
        'status': 'active',
        'sort': 'renewal_date',
        'due_within': 30,
    })
    return f'{base}?{query}'


def _build_upcoming_item(subscription, index, today):
    effective_cost = subscription.user_cost if subscription.is_shared else subscription.cost
    return {
        'is_placeholder': False,
        'bg_class': _service_theme(subscription.service_name, index),
        'service_name': subscription.service_name,
        'amount': _format_money(effective_cost, subscription.currency),
        'days_left_text': _days_left_text(subscription.renewal_date, today),
        'edit_url': reverse('subscriptions:update', args=[subscription.pk]),
        'icon_url': subscription.get_icon_url(),
        'icon_fallback': subscription.get_fallback_icon(),
    }


def _build_upcoming_placeholder(index):
    data = PLACEHOLDER_UPCOMING.copy()
    data.update(
        {
            'is_placeholder': True,
            'bg_class': CARD_THEME_ROTATION[index % len(CARD_THEME_ROTATION)],
            'edit_url': '',
            'icon_url': '',
            'icon_fallback': '+',
        }
    )
    return data


def _build_subscription_panel_item(subscription, index):
    return {
        'is_placeholder': False,
        'bg_class': _service_theme(subscription.service_name, index),
        'title': subscription.service_name,
        'subtitle': f"{_format_money(_monthly_cost(subscription), subscription.currency)}/monthly",
        'create_url': (
            reverse('subscriptions:create')
            + '?'
            + urlencode(
                {
                    'service_name': subscription.service_name,
                    'category': subscription.category,
                    'billing_cycle': subscription.billing_cycle,
                }
            )
        ),
        'icon_url': subscription.get_icon_url(),
        'icon_fallback': subscription.get_fallback_icon(),
    }


def _build_subscription_placeholder(index):
    data = PLACEHOLDER_SUBSCRIPTION.copy()
    data.update(
        {
            'is_placeholder': True,
            'bg_class': CARD_THEME_ROTATION[index % len(CARD_THEME_ROTATION)],
            'create_url': '',
            'icon_url': '',
            'icon_fallback': '+',
        }
    )
    return data


def _duration_label(subscription):
    mapping = {
        'weekly': '1 week',
        'monthly': '1 month',
        'yearly': '1 year',
    }
    return mapping.get(subscription.billing_cycle, '1 month')


def _build_active_item(subscription, index):
    effective_cost = subscription.user_cost if subscription.is_shared else subscription.cost
    card_last4 = subscription.card.last4 if subscription.card else None
    return {
        'is_placeholder': False,
        'bg_class': _service_theme(subscription.service_name, index),
        'title': subscription.service_name,
        'duration_label': _duration_label(subscription),
        'amount': _format_money(effective_cost, subscription.currency),
        'payment_info': f"Payment info: **** {card_last4}" if card_last4 else 'Payment info: Not set',
        'plan_details': f"Plan details: {subscription.plan_name}" if subscription.plan_name else f"Plan details: {subscription.billing_cycle.title()}",
        'edit_url': reverse('subscriptions:update', args=[subscription.pk]),
        'icon_url': subscription.get_icon_url(),
        'icon_fallback': subscription.get_fallback_icon(),
    }


def _build_active_placeholder(index):
    data = PLACEHOLDER_ACTIVE.copy()
    data.update(
        {
            'is_placeholder': True,
            'bg_class': CARD_THEME_ROTATION[index % len(CARD_THEME_ROTATION)],
            'edit_url': '',
            'icon_url': '',
            'icon_fallback': '+',
        }
    )
    return data


def _build_transaction_item(transaction, index):
    return {
        'is_placeholder': False,
        'bg_class': _service_theme(transaction.service_name_snapshot, index),
        'title': transaction.service_name_snapshot,
        'timestamp': timezone.localtime(transaction.charged_at).strftime('%b %d, %I:%M %p'),
        'amount': f"-{_format_money(transaction.amount, transaction.currency)}",
    }


def _build_transaction_placeholder(index):
    data = PLACEHOLDER_TRANSACTION.copy()
    data.update(
        {
            'is_placeholder': True,
            'bg_class': CARD_THEME_ROTATION[index % len(CARD_THEME_ROTATION)],
        }
    )
    return data


def build_dashboard_view_model(user, today=None):
    today = today or timezone.localdate()
    next_30_days = today + timedelta(days=30)

    user_subs = Subscription.objects.filter(user=user).select_related('card')
    # Keep long-lived records in sync so dashboard cards always show current renewal data.
    for subscription in user_subs.filter(status='active'):
        refresh_subscription_renewal_date(subscription)

    active_subs = user_subs.filter(status='active').order_by('renewal_date', 'service_name')
    paused_subs = user_subs.filter(status='paused')
    cancelled_subs = user_subs.filter(status='cancelled')
    shared_subs = user_subs.filter(status='active', is_shared=True)
    upcoming_renewals = active_subs.filter(renewal_date__range=[today, next_30_days])

    monthly_spend = Decimal('0.00')
    monthly_spend_by_currency = {}
    for sub in active_subs:
        monthly_cost = _monthly_cost(sub)
        currency = (sub.currency or 'USD').upper()
        monthly_spend += monthly_cost
        monthly_spend_by_currency[currency] = (
            monthly_spend_by_currency.get(currency, Decimal('0.00')) + monthly_cost
        )

    yearly_spend = monthly_spend * Decimal('12')
    active_count = active_subs.count()
    paused_count = paused_subs.count()
    cancelled_count = cancelled_subs.count()
    shared_count = shared_subs.count()
    avg_monthly_spend = (
        monthly_spend / Decimal(active_count)
        if active_count
        else Decimal('0.00')
    )

    upcoming_items = [
        _build_upcoming_item(sub, index, today)
        for index, sub in enumerate(upcoming_renewals[:3])
    ]
    subscription_panel_items = [
        _build_subscription_panel_item(sub, index)
        for index, sub in enumerate(active_subs[:3])
    ]
    active_panel_items = [
        _build_active_item(sub, index)
        for index, sub in enumerate(active_subs[:2])
    ]
    recent_transactions_qs = Transaction.objects.filter(user=user).select_related('subscription')[:2]
    recent_transaction_items = [
        _build_transaction_item(txn, index)
        for index, txn in enumerate(recent_transactions_qs)
    ]

    upcoming_bills = _slot_pad(upcoming_items, 3, _build_upcoming_placeholder)
    subscriptions_panel = _slot_pad(subscription_panel_items, 3, _build_subscription_placeholder)
    active_subscriptions_panel = _slot_pad(active_panel_items, 2, _build_active_placeholder)
    recent_transactions = _slot_pad(recent_transaction_items, 2, _build_transaction_placeholder)

    next_renewal = upcoming_renewals.first()
    chip_date = next_renewal.renewal_date.strftime('%m/%d') if next_renewal and next_renewal.renewal_date else '--/--'

    return {
        # Header / actions
        'avatar_initial': (user.email or 'U')[:1].upper(),
        'greeting_name': _greeting_name(user.email),
        'bell_url': _renewal_view_all_url(),
        'upcoming_view_all_url': _renewal_view_all_url(),
        'subscriptions_view_all_url': reverse('subscriptions:list'),
        # Main balance block
        'monthly_spend_display': _format_currency_breakdown(monthly_spend_by_currency),
        'balance_chip_date': chip_date,
        # Dashboard sections
        'upcoming_bills': upcoming_bills,
        'subscriptions_panel': subscriptions_panel,
        'active_subscriptions_panel': active_subscriptions_panel,
        'recent_transactions': recent_transactions,
        # Compatibility keys for existing tests/consumers
        'total_active': active_count,
        'total_paused': paused_count,
        'total_cancelled': cancelled_count,
        'total_shared': shared_count,
        'active_subscriptions': active_subs,
        'paused_subscriptions': paused_subs,
        'cancelled_subscriptions': cancelled_subs,
        'shared_subscriptions': shared_subs,
        'monthly_spend': _quantize_money(monthly_spend),
        'monthly_spend_by_currency': {
            currency: _quantize_money(amount)
            for currency, amount in sorted(monthly_spend_by_currency.items(), key=lambda item: item[0])
        },
        'yearly_spend': _quantize_money(yearly_spend),
        'avg_monthly_spend': _quantize_money(avg_monthly_spend),
        'upcoming_renewals': upcoming_renewals,
        'status_dist': {
            'active': active_count,
            'cancelled': cancelled_count,
            'paused': paused_count,
            'shared': shared_count,
        },
    }
