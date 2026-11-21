from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlencode

from django.urls import reverse
from django.utils import timezone

from subscriptions.models import Subscription, Transaction
from subscriptions.money import monthly_equivalent
from subscriptions.services import effective_renewal_date, renewals_between

from .constants import (
    CARD_THEME_ROTATION,
    PLACEHOLDER_ACTIVE,
    PLACEHOLDER_SUBSCRIPTION,
    PLACEHOLDER_UPCOMING,
)
from .models import BalanceAdjustment
from .service_colors import build_service_color_map, service_background_style


VALID_DASHBOARD_SCOPES = set(BalanceAdjustment.Scope.values)


def charges_for_scope(user, scope):
    if scope == 'teams':
        return Transaction.objects.filter(team__memberships__user=user)
    return Transaction.objects.filter(user=user, team__isnull=True)


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


def _format_signed_money(amount, currency='USD'):
    quantized = _quantize_money(amount)
    sign = '+' if quantized >= Decimal('0.00') else '-'
    absolute_amount = quantized.copy_abs()
    return f"{sign}{_format_money(absolute_amount, currency)}"


def _format_currency_breakdown(totals):
    if not totals:
        return _format_money(Decimal('0.00'), 'USD')

    ordered = sorted(totals.items(), key=lambda item: item[0])
    parts = [_format_money(amount, currency) for currency, amount in ordered]
    return ' + '.join(parts)


def _normalize_dashboard_scope(scope):
    normalized_scope = (scope or 'personal').lower()
    if normalized_scope not in VALID_DASHBOARD_SCOPES:
        return 'personal'
    return normalized_scope


def _subscriptions_for_scope(user, scope):
    normalized_scope = _normalize_dashboard_scope(scope)
    if normalized_scope == 'teams':
        queryset = (
            Subscription.objects.filter(team__memberships__user=user)
            .select_related('card', 'team', 'user')
            .distinct()
        )
    else:
        queryset = Subscription.objects.filter(user=user, team__isnull=True).select_related('card')
    return queryset.prefetch_related('price_changes', 'participants'), normalized_scope


def _build_balance_trend_points(transactions, today, window_days=30, currency=None):
    window_days = max(2, int(window_days or 30))
    start_date = today - timedelta(days=window_days - 1)
    totals_by_currency_and_date = {}
    available_currencies = set()

    recent_transactions = transactions.filter(charged_for_date__range=[start_date, today]).only(
        'charged_for_date', 'amount', 'currency'
    )
    for transaction in recent_transactions:
        code = (transaction.currency or 'USD').upper()
        available_currencies.add(code)
        currency_totals = totals_by_currency_and_date.setdefault(code, {})
        running_total = currency_totals.get(transaction.charged_for_date, Decimal('0.00'))
        currency_totals[transaction.charged_for_date] = running_total + transaction.amount

    if currency:
        selected_currency = currency
    elif not available_currencies:
        selected_currency = 'USD'
    elif 'USD' in available_currencies:
        selected_currency = 'USD'
    elif len(available_currencies) == 1:
        selected_currency = next(iter(available_currencies))
    else:
        selected_currency = sorted(available_currencies)[0]

    totals_by_date = totals_by_currency_and_date.get(selected_currency, {})

    points = []
    has_activity = False
    for offset in range(window_days):
        point_date = start_date + timedelta(days=offset)
        amount = _quantize_money(totals_by_date.get(point_date, Decimal('0.00')))
        has_activity = has_activity or amount != Decimal('0.00')
        points.append(float(amount))

    omitted_currencies = sorted(currency for currency in available_currencies if currency != selected_currency)

    return {
        'points': points,
        'start_label': start_date.strftime('%b %d'),
        'end_label': today.strftime('%b %d'),
        'has_activity': has_activity,
        'currency': selected_currency,
        'has_multiple_currencies': bool(omitted_currencies),
        'omitted_currencies': omitted_currencies,
    }


def _monthly_spend_by_currency(subscriptions, today):
    totals = {}
    for subscription in subscriptions:
        monthly_cost = _monthly_cost(subscription, today)
        currency = (subscription.currency or 'USD').upper()
        totals[currency] = totals.get(currency, Decimal('0.00')) + monthly_cost
    return totals


def monthly_spend_for_scope(user, scope, currency):
    subscriptions, _ = _subscriptions_for_scope(user, scope)
    today = timezone.localdate()
    plans = subscriptions.filter(currency__iexact=currency).exclude(status='cancelled')
    return _quantize_money(sum((_monthly_cost(sub, today) for sub in plans if sub.bills_on(today)), Decimal('0')))


def _build_balance_snapshot(user, monthly_spend_by_currency, scope, currency='USD'):
    base_balance = _quantize_money(monthly_spend_by_currency.get(currency, Decimal('0.00')))
    adjustment_amount = _quantize_money(
        BalanceAdjustment.objects.filter(user=user, scope=scope, currency=currency)
        .values_list('amount', flat=True)
        .first()
        or Decimal('0.00')
    )
    adjusted_balance = _quantize_money(base_balance + adjustment_amount)
    return {
        'display': _format_money(adjusted_balance, currency),
        'base_display': _format_money(base_balance, currency),
        'adjustment_display': _format_signed_money(adjustment_amount, currency),
        'adjustment_amount': float(adjustment_amount),
        'adjusted_amount': float(adjusted_balance),
        'base_amount': float(base_balance),
    }


def set_user_balance_target(user, target_balance, scope='personal', currency='USD'):
    normalized_scope = _normalize_dashboard_scope(scope)
    base_balance = monthly_spend_for_scope(user, normalized_scope, currency)
    target_balance = _quantize_money(target_balance)
    adjustment_amount = _quantize_money(target_balance - base_balance)

    BalanceAdjustment.objects.update_or_create(
        user=user, scope=normalized_scope, currency=currency, defaults={'amount': adjustment_amount},
    )

    return {
        'balance_display': _format_money(target_balance, currency),
        'balance_base_display': _format_money(base_balance, currency),
        'balance_adjustment_display': _format_signed_money(adjustment_amount, currency),
        'balance_adjustment_amount': float(adjustment_amount),
        'balance_adjusted_amount': float(target_balance),
        'balance_base_amount': float(base_balance),
        'dashboard_scope': normalized_scope,
    }


def _monthly_cost(subscription, today):
    cost = subscription.share_on(today)
    return monthly_equivalent(cost, subscription.billing_cycle)


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


def _subscription_destination_url(subscription):
    if subscription.team_id:
        return reverse('accounts:team_detail', args=[subscription.team_id])
    return reverse('subscriptions:update', args=[subscription.pk])


def _build_upcoming_item(subscription, renewal_date, today, service_color_map):
    effective_cost = subscription.share_on(renewal_date)
    return {
        'date': renewal_date.isoformat(),
        'id': subscription.pk,
        'is_placeholder': False,
        'bg_class': '',
        'bg_style': service_background_style(subscription.service_name, service_color_map),
        'service_name': subscription.service_name,
        'amount': _format_money(effective_cost, subscription.currency),
        'days_left_text': _days_left_text(renewal_date, today),
        'edit_url': _subscription_destination_url(subscription),
        'icon_url': subscription.get_icon_url(),
        'icon_fallback': subscription.get_fallback_icon(),
    }


def _build_upcoming_placeholder(index):
    data = PLACEHOLDER_UPCOMING.copy()
    data.update(
        {
            'is_placeholder': True,
            'bg_class': CARD_THEME_ROTATION[index % len(CARD_THEME_ROTATION)],
            'bg_style': '',
            'edit_url': '',
            'icon_url': '',
            'icon_fallback': '+',
        }
    )
    return data


def _build_subscription_panel_item(subscription, today, service_color_map):
    create_query = {
        'service_name': subscription.service_name,
        'category': subscription.category,
        'billing_cycle': subscription.billing_cycle,
    }
    if subscription.team_id:
        create_query['team'] = subscription.team_id

    return {
        'is_placeholder': False,
        'bg_class': '',
        'bg_style': service_background_style(subscription.service_name, service_color_map),
        'title': subscription.service_name,
        'subtitle': f"{_format_money(_monthly_cost(subscription, today), subscription.currency)}/monthly",
        'create_url': (
            reverse('subscriptions:create')
            + '?'
            + urlencode(create_query)
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
            'bg_style': '',
            'create_url': '',
            'icon_url': '',
            'icon_fallback': '+',
        }
    )
    return data


def _duration_label(subscription):
    mapping = {
        'weekly': '1 week',
        'quarterly': '3 months',
        'halfyearly': '6 months',
        'fourweekly': '28 days',
        'monthly': '1 month',
        'yearly': '1 year',
    }
    return mapping.get(subscription.billing_cycle, '1 month')


def _build_active_item(subscription, today, service_color_map):
    effective_cost = subscription.share_on(today)
    card_last4 = subscription.card.last4 if subscription.card else None
    return {
        'id': subscription.pk,
        'is_placeholder': False,
        'bg_class': '',
        'bg_style': service_background_style(subscription.service_name, service_color_map),
        'title': subscription.service_name,
        'duration_label': _duration_label(subscription),
        'amount': _format_money(effective_cost, subscription.currency),
        'payment_info': f"Payment info: **** {card_last4}" if card_last4 else 'Payment info: Not set',
        'plan_details': f"Plan details: {subscription.plan_name}" if subscription.plan_name else f"Plan details: {subscription.billing_cycle.title()}",
        'edit_url': _subscription_destination_url(subscription),
        'icon_url': subscription.get_icon_url(),
        'icon_fallback': subscription.get_fallback_icon(),
    }


def _build_active_placeholder(index):
    data = PLACEHOLDER_ACTIVE.copy()
    data.update(
        {
            'is_placeholder': True,
            'bg_class': CARD_THEME_ROTATION[index % len(CARD_THEME_ROTATION)],
            'bg_style': '',
            'edit_url': '',
            'icon_url': '',
            'icon_fallback': '+',
        }
    )
    return data


def _build_transaction_item(transaction, index, service_color_map):
    return {
        'id': transaction.pk,
        'is_placeholder': False,
        'bg_class': '',
        'swatch_style': service_background_style(transaction.service_name_snapshot, service_color_map),
        'title': transaction.service_name_snapshot,
        'timestamp': transaction.charged_for_date.strftime('%b %d, %Y'),
        'amount': f"-{_format_money(transaction.amount, transaction.currency)}",
    }


def build_dashboard_view_model(user, today=None, scope='personal', selected_currency=None):
    today = today or timezone.localdate()
    window_end = today + timedelta(days=29)

    user_subs, scope = _subscriptions_for_scope(user, scope)
    transactions = charges_for_scope(user, scope)

    if scope == 'teams':
        view_all_url = reverse('accounts:teams_overview')
    else:
        view_all_url = _renewal_view_all_url()

    active_subs, paused_subs, cancelled_subs = [], [], []
    for sub in user_subs:
        if sub.bills_on(today):
            active_subs.append(sub)
        elif sub.status == 'cancelled' or sub.cancellation_state == 'confirmed':
            cancelled_subs.append(sub)
        else:
            paused_subs.append(sub)
    active_subs.sort(key=lambda sub: (
        effective_renewal_date(sub, today) or date.max, sub.service_name.lower(), sub.pk,
    ))
    active_subs_qs = user_subs.filter(pk__in=[sub.pk for sub in active_subs])
    shared_subs = active_subs_qs.filter(is_shared=True)
    occurrences = sorted(
        ((day, sub) for sub in active_subs + paused_subs for day in renewals_between(sub, today, window_end)),
        key=lambda event: (event[0], event[1].service_name.lower(), event[1].pk),
    )
    upcoming_renewals = [sub for _, sub in occurrences]

    monthly_spend_by_currency = _monthly_spend_by_currency(active_subs, today)
    paused_spend_by_currency = _monthly_spend_by_currency(paused_subs, today)
    cancelled_spend_by_currency = _monthly_spend_by_currency(cancelled_subs, today)
    upcoming_total_by_currency = {}
    for day, sub in occurrences:
        currency = (sub.currency or 'USD').upper()
        charge_amount = sub.share_on(day)
        upcoming_total_by_currency[currency] = (
            upcoming_total_by_currency.get(currency, Decimal('0.00')) + charge_amount
        )
    total_subscriptions_balance_by_currency = {}
    for totals in (monthly_spend_by_currency, paused_spend_by_currency, cancelled_spend_by_currency):
        for currency, amount in totals.items():
            total_subscriptions_balance_by_currency[currency] = (
                total_subscriptions_balance_by_currency.get(currency, Decimal('0.00')) + amount
            )

    balance_currency = selected_currency or 'USD'
    monthly_spend = monthly_spend_by_currency.get(balance_currency, Decimal('0.00'))
    yearly_spend = monthly_spend * Decimal('12')
    active_count = len(active_subs)
    currency_active_count = sum(
        1 for sub in active_subs if (sub.currency or 'USD').upper() == balance_currency
    )
    paused_count = len(paused_subs)
    cancelled_count = len(cancelled_subs)
    shared_count = sum(sub.is_shared for sub in active_subs)
    avg_monthly_spend = (
        monthly_spend / Decimal(currency_active_count)
        if currency_active_count
        else Decimal('0.00')
    )

    recent_transactions_qs = list(
        transactions
        .order_by('-charged_for_date', '-pk')[:2]
    )
    service_color_map = build_service_color_map(active_subs + upcoming_renewals, recent_transactions_qs)

    upcoming_items = [
        _build_upcoming_item(sub, day, today, service_color_map)
        for day, sub in occurrences
    ]
    subscription_panel_items = [
        _build_subscription_panel_item(sub, today, service_color_map)
        for sub in active_subs[:3]
    ]
    active_panel_items = [
        _build_active_item(sub, today, service_color_map)
        for sub in active_subs
    ]
    recent_transaction_items = [
        _build_transaction_item(txn, index, service_color_map)
        for index, txn in enumerate(recent_transactions_qs)
    ]

    upcoming_bills = (
        upcoming_items
        if upcoming_items
        else _slot_pad(upcoming_items, 3, _build_upcoming_placeholder)
    )
    subscriptions_panel = _slot_pad(subscription_panel_items, 3, _build_subscription_placeholder)
    active_subscriptions_panel = (
        active_panel_items
        if active_panel_items
        else _slot_pad(active_panel_items, 2, _build_active_placeholder)
    )
    recent_transactions = recent_transaction_items

    chip_date = occurrences[0][0].strftime('%m/%d') if occurrences else '--/--'
    balance_trend = _build_balance_trend_points(transactions, today, window_days=30, currency=selected_currency)
    adjustments = BalanceAdjustment.objects.filter(user=user, scope=scope)
    monthly_limit = adjustments.filter(currency=balance_currency).values_list('monthly_limit', flat=True).first()
    balance_snapshot = _build_balance_snapshot(user, monthly_spend_by_currency, scope, balance_currency)
    currencies = set(total_subscriptions_balance_by_currency) | set(adjustments.values_list('currency', flat=True))
    currencies.update(transactions.order_by().values_list('currency', flat=True).distinct())
    currencies.update([balance_currency, user.preferred_currency or 'USD', 'USD'])
    omitted_currencies = balance_trend['omitted_currencies']
    if omitted_currencies:
        omitted_text = ', '.join(omitted_currencies)
        trend_note = f"Showing {balance_trend['currency']} charges only. Also found: {omitted_text}."
    else:
        trend_note = ''

    return {
        # Header / actions
        'avatar_initial': (user.email or 'U')[:1].upper(),
        'greeting_name': _greeting_name(user.email),
        'bell_url': reverse('dashboard:notifications_page'),
        'upcoming_view_all_url': view_all_url,
        'subscriptions_view_all_url': reverse('accounts:teams_overview') if scope == 'teams' else reverse('subscriptions:list'),
        'dashboard_scope': scope,
        'currency_options': sorted(currencies),
        'balance_currency': balance_currency,
        'monthly_limit': str(monthly_limit) if monthly_limit is not None else None,
        'over_budget': monthly_limit is not None and _quantize_money(monthly_spend_by_currency.get(balance_currency, Decimal('0'))) > monthly_limit,
        # Main balance block
        'balance_display': balance_snapshot['display'],
        'balance_base_display': balance_snapshot['base_display'],
        'balance_adjustment_display': balance_snapshot['adjustment_display'],
        'balance_adjustment_amount': balance_snapshot['adjustment_amount'],
        'balance_adjusted_amount': balance_snapshot['adjusted_amount'],
        'balance_base_amount': balance_snapshot['base_amount'],
        'monthly_spend_display': _format_currency_breakdown(monthly_spend_by_currency),
        'balance_chip_date': chip_date,
        'balance_trend_points': balance_trend['points'],
        'balance_trend_start_label': balance_trend['start_label'],
        'balance_trend_end_label': balance_trend['end_label'],
        'balance_trend_has_activity': balance_trend['has_activity'],
        'balance_trend_currency': balance_trend['currency'],
        'balance_trend_has_multiple_currencies': balance_trend['has_multiple_currencies'],
        'balance_trend_note': trend_note,
        'stats_upcoming_bill_balance_display': _format_currency_breakdown(upcoming_total_by_currency),
        'stats_total_subscriptions_balance_display': _format_currency_breakdown(total_subscriptions_balance_by_currency),
        'stats_total_active': _format_currency_breakdown(monthly_spend_by_currency),
        'stats_total_paused': _format_currency_breakdown(paused_spend_by_currency),
        'stats_total_cancelled': _format_currency_breakdown(cancelled_spend_by_currency),
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
        'active_subscriptions': active_subs_qs,
        'paused_subscriptions': user_subs.filter(pk__in=[sub.pk for sub in paused_subs]),
        'cancelled_subscriptions': user_subs.filter(pk__in=[sub.pk for sub in cancelled_subs]),
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
