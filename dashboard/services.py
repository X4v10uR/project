from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import colorsys
import hashlib
import re
import sys
from functools import lru_cache
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from django.urls import reverse
from django.utils import timezone

from subscriptions.money import monthly_equivalent
from subscriptions.models import Subscription, Transaction
from subscriptions.color_utils import normalize_subscription_display_color

from .models import BalanceAdjustment
from .constants import (
    CARD_COLOR_PALETTE,
    CARD_THEME_ROTATION,
    PLACEHOLDER_ACTIVE,
    PLACEHOLDER_SUBSCRIPTION,
    PLACEHOLDER_UPCOMING,
    SERVICE_COLOR_PREFERENCES,
)


VALID_DASHBOARD_SCOPES = {'personal', 'teams'}
HEX_COLOR_TOKEN_PATTERN = re.compile(r'#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b')
RGB_COLOR_TOKEN_PATTERN = re.compile(r'rgba?\(([^)]+)\)', re.IGNORECASE)
NAMED_COLOR_TOKEN_PATTERN = re.compile(
    r'\b(?:black|white|red|green|blue|yellow|orange|purple|pink|brown|gray|grey)\b',
    re.IGNORECASE,
)
ICON_BRAND_DOMINANT_COLORS = {
    'netflix': '#e50914',
    'spotify': '#1db954',
    'apple': '#000000',
    'apple-tv': '#000000',
    'youtube': '#ff0000',
    'disney-plus': '#113ccf',
    'paramount-plus': '#0064ff',
    'adobe': '#ff0000',
    'amazon-prime-video': '#00a8e1',
}
NAMED_COLOR_HEX = {
    'black': '#000000',
    'white': '#ffffff',
    'red': '#ff0000',
    'green': '#008000',
    'blue': '#0000ff',
    'yellow': '#ffff00',
    'orange': '#ffa500',
    'purple': '#800080',
    'pink': '#ffc0cb',
    'brown': '#a52a2a',
    'gray': '#808080',
    'grey': '#808080',
}


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
    return queryset, normalized_scope


def _build_balance_trend_points(user, today, window_days=30):
    window_days = max(2, int(window_days or 30))
    start_date = today - timedelta(days=window_days - 1)
    totals_by_currency_and_date = {}
    available_currencies = set()

    recent_transactions = Transaction.objects.filter(
        user=user,
        charged_for_date__range=[start_date, today],
    ).only('charged_for_date', 'amount', 'currency')
    for transaction in recent_transactions:
        currency = (transaction.currency or 'USD').upper()
        available_currencies.add(currency)
        currency_totals = totals_by_currency_and_date.setdefault(currency, {})
        running_total = currency_totals.get(transaction.charged_for_date, Decimal('0.00'))
        currency_totals[transaction.charged_for_date] = running_total + transaction.amount

    if not available_currencies:
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


def _monthly_spend_by_currency(active_subscriptions):
    totals = {}
    for subscription in active_subscriptions:
        monthly_cost = _monthly_cost(subscription)
        currency = (subscription.currency or 'USD').upper()
        totals[currency] = totals.get(currency, Decimal('0.00')) + monthly_cost
    return totals


def _usd_monthly_spend_for_scope(user, scope='personal'):
    total = Decimal('0.00')
    subscriptions_queryset, _ = _subscriptions_for_scope(user, scope)
    active_subs = subscriptions_queryset.filter(status='active')
    for subscription in active_subs:
        if (subscription.currency or 'USD').upper() != 'USD':
            continue
        total += _monthly_cost(subscription)
    return _quantize_money(total)


def _build_balance_snapshot(user, monthly_spend_by_currency):
    base_balance = _quantize_money(monthly_spend_by_currency.get('USD', Decimal('0.00')))
    adjustment_amount = _quantize_money(
        BalanceAdjustment.objects.filter(user=user)
        .values_list('amount', flat=True)
        .first()
        or Decimal('0.00')
    )
    adjusted_balance = _quantize_money(base_balance + adjustment_amount)
    return {
        'display': _format_money(adjusted_balance, 'USD'),
        'base_display': _format_money(base_balance, 'USD'),
        'adjustment_display': _format_signed_money(adjustment_amount, 'USD'),
        'adjustment_amount': float(adjustment_amount),
        'adjusted_amount': float(adjusted_balance),
        'base_amount': float(base_balance),
    }


def set_user_balance_target(user, target_balance, scope='personal'):
    normalized_scope = _normalize_dashboard_scope(scope)
    base_balance = _usd_monthly_spend_for_scope(user, scope=normalized_scope)
    target_balance = _quantize_money(target_balance)
    adjustment_amount = _quantize_money(target_balance - base_balance)

    adjustment_record, _ = BalanceAdjustment.objects.get_or_create(
        user=user,
        defaults={'amount': Decimal('0.00')},
    )
    adjustment_record.amount = adjustment_amount
    adjustment_record.save(update_fields=['amount', 'updated_at'])

    return {
        'balance_display': _format_money(target_balance, 'USD'),
        'balance_base_display': _format_money(base_balance, 'USD'),
        'balance_adjustment_display': _format_signed_money(adjustment_amount, 'USD'),
        'balance_adjustment_amount': float(adjustment_amount),
        'balance_adjusted_amount': float(target_balance),
        'balance_base_amount': float(base_balance),
        'dashboard_scope': normalized_scope,
    }


def _monthly_cost(subscription):
    cost = subscription.user_cost if subscription.is_shared else subscription.cost
    return monthly_equivalent(cost, subscription.billing_cycle)


def _effective_renewal_date(subscription, today):
    if subscription.renewal_date and subscription.renewal_date >= today:
        return subscription.renewal_date
    return subscription.calculate_renewal_date()


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


def _normalized_service_name(service_name):
    return (service_name or '').strip().lower()


def _stable_bucket(value):
    digest = hashlib.sha256(value.encode('utf-8')).hexdigest()
    return int(digest[:8], 16)


def _hex_to_rgb(color):
    if not color:
        return None

    token = color.strip().lower()
    if not token.startswith('#'):
        return None

    if len(token) == 4:
        token = '#' + ''.join(channel * 2 for channel in token[1:])
    elif len(token) == 9:
        token = token[:7]

    if len(token) != 7:
        return None

    try:
        return (
            int(token[1:3], 16),
            int(token[3:5], 16),
            int(token[5:7], 16),
        )
    except ValueError:
        return None


def _rgb_to_hex(r, g, b):
    return f'#{max(0, min(255, int(round(r)))):02x}{max(0, min(255, int(round(g)))):02x}{max(0, min(255, int(round(b)))):02x}'


def _named_color_to_hex(token):
    normalized = (token or '').strip().lower()
    return NAMED_COLOR_HEX.get(normalized, '')


def _normalize_color_token(token):
    value = (token or '').strip().lower()
    if not value or value in {'none', 'transparent', 'currentcolor', 'inherit'}:
        return ''

    if value.startswith('#'):
        rgb = _hex_to_rgb(value)
        if not rgb:
            return ''
        return _rgb_to_hex(*rgb)

    rgb_match = RGB_COLOR_TOKEN_PATTERN.fullmatch(value)
    if rgb_match:
        parts = [part.strip() for part in rgb_match.group(1).split(',')]
        if len(parts) < 3:
            return ''

        channels = []
        for part in parts[:3]:
            if part.endswith('%'):
                try:
                    percent = float(part[:-1])
                except ValueError:
                    return ''
                channels.append(max(0, min(255, round((percent / 100.0) * 255))))
                continue
            try:
                channels.append(max(0, min(255, round(float(part)))))
            except ValueError:
                return ''

        return _rgb_to_hex(*channels)

    return _named_color_to_hex(value)


def _extract_svg_dominant_color(svg_markup):
    if not svg_markup:
        return ''

    color_count = {}

    for match in HEX_COLOR_TOKEN_PATTERN.finditer(svg_markup):
        color = _normalize_color_token(match.group(0))
        if color:
            color_count[color] = color_count.get(color, 0) + 1

    for match in RGB_COLOR_TOKEN_PATTERN.finditer(svg_markup):
        color = _normalize_color_token(match.group(0))
        if color:
            color_count[color] = color_count.get(color, 0) + 1

    for match in NAMED_COLOR_TOKEN_PATTERN.finditer(svg_markup):
        color = _normalize_color_token(match.group(0))
        if color:
            color_count[color] = color_count.get(color, 0) + 1

    if not color_count:
        return ''

    ranked = sorted(color_count.items(), key=lambda item: item[1], reverse=True)

    vibrant = []
    neutral = []
    for color, count in ranked:
        rgb = _hex_to_rgb(color)
        if not rgb:
            continue

        red, green, blue = [channel / 255.0 for channel in rgb]
        hue, lightness, saturation = colorsys.rgb_to_hls(red, green, blue)

        if lightness > 0.96:
            continue

        if saturation >= 0.2 and 0.12 <= lightness <= 0.88:
            vibrant.append((color, count))
        else:
            neutral.append((color, count))

    if vibrant:
        return vibrant[0][0]
    if neutral:
        return neutral[0][0]
    return ranked[0][0]


def _is_test_runtime():
    return any(argument == 'test' for argument in sys.argv[1:])


@lru_cache(maxsize=256)
def _dominant_icon_color(icon_url):
    if not icon_url:
        return ''

    parsed = urlparse(icon_url)
    if parsed.scheme not in {'http', 'https'}:
        return ''

    slug = parsed.path.rsplit('/', 1)[-1].split('.', 1)[0].lower()
    mapped = ICON_BRAND_DOMINANT_COLORS.get(slug)
    if mapped:
        return mapped

    if _is_test_runtime():
        return ''

    request = Request(icon_url, headers={'User-Agent': 'SublyDashboard/1.0'})
    try:
        with urlopen(request, timeout=0.45) as response:
            raw_content = response.read(120000)
    except (HTTPError, URLError, TimeoutError, OSError):
        return ''

    svg_markup = raw_content.decode('utf-8', errors='ignore')
    return _extract_svg_dominant_color(svg_markup)


def _soften_color_for_card(color):
    rgb = _hex_to_rgb(color)
    if not rgb:
        return ''

    red, green, blue = [channel / 255.0 for channel in rgb]
    hue, lightness, saturation = colorsys.rgb_to_hls(red, green, blue)

    if saturation < 0.08:
        adjusted_saturation = 0.08
        adjusted_lightness = 0.68 if lightness >= 0.6 else 0.6
    else:
        # Keep the original hue but mute saturation/lightness so cards stay calm.
        adjusted_saturation = max(0.24, min(0.52, saturation * 0.68))
        adjusted_lightness = max(0.56, min(0.64, lightness + 0.14))

    softened_red, softened_green, softened_blue = colorsys.hls_to_rgb(
        hue, adjusted_lightness, adjusted_saturation
    )
    return _rgb_to_hex(softened_red * 255, softened_green * 255, softened_blue * 255)


def _ensure_distinct_color(candidate, seed_text, used_colors):
    if not candidate:
        return _pick_distinct_palette_color(seed_text, used_colors)

    if candidate not in used_colors:
        return candidate

    rgb = _hex_to_rgb(candidate)
    if not rgb:
        return _pick_distinct_palette_color(seed_text, used_colors)

    red, green, blue = [channel / 255.0 for channel in rgb]
    hue, lightness, saturation = colorsys.rgb_to_hls(red, green, blue)

    for delta in (0.05, -0.05, 0.1, -0.1, 0.15, -0.15):
        nudged_lightness = min(max(lightness + delta, 0.2), 0.82)
        nudged_red, nudged_green, nudged_blue = colorsys.hls_to_rgb(
            hue, nudged_lightness, saturation
        )
        nudged_color = _rgb_to_hex(
            nudged_red * 255, nudged_green * 255, nudged_blue * 255
        )
        if nudged_color not in used_colors:
            return nudged_color

    return _pick_distinct_palette_color(seed_text, used_colors)


def _generate_pastel_color(seed_text, used_colors):
    base_hue = _stable_bucket(seed_text) % 360
    for offset in range(0, 360, 17):
        candidate = f"hsl({(base_hue + offset) % 360} 65% 74%)"
        if candidate not in used_colors:
            return candidate
    return f"hsl({base_hue} 65% 74%)"


def _pick_distinct_palette_color(seed_text, used_colors):
    if not CARD_COLOR_PALETTE:
        return _generate_pastel_color(seed_text, used_colors)

    start_index = _stable_bucket(seed_text) % len(CARD_COLOR_PALETTE)
    for step in range(len(CARD_COLOR_PALETTE)):
        candidate = CARD_COLOR_PALETTE[(start_index + step) % len(CARD_COLOR_PALETTE)]
        if candidate not in used_colors:
            return candidate
    return _generate_pastel_color(seed_text, used_colors)


def _build_service_color_map(active_subscriptions, recent_transactions):
    service_order = []
    custom_colors = {}

    def _add_service(name, color=""):
        normalized = _normalized_service_name(name)
        if normalized and normalized not in service_order:
            service_order.append(normalized)
        normalized_color = normalize_subscription_display_color(color)
        if normalized and normalized_color and normalized not in custom_colors:
            custom_colors[normalized] = normalized_color

    for subscription in active_subscriptions:
        _add_service(subscription.service_name, getattr(subscription, "display_color", ""))
    for transaction in recent_transactions:
        _add_service(transaction.service_name_snapshot)

    used_colors = set()
    color_map = {}

    for normalized in service_order:
        custom_color = custom_colors.get(normalized)
        if custom_color:
            color_map[normalized] = custom_color
            continue

        preferred = SERVICE_COLOR_PREFERENCES.get(normalized)
        if preferred:
            color = _ensure_distinct_color(preferred, normalized, used_colors)
        else:
            # Use a lighter randomized-looking palette assignment, not logo-derived colors.
            color = _pick_distinct_palette_color(normalized, used_colors)

        color_map[normalized] = color
        used_colors.add(color)

    return color_map


def _service_bg_style(service_name, service_color_map):
    normalized = _normalized_service_name(service_name)
    color = service_color_map.get(normalized)
    if not color:
        color = _pick_distinct_palette_color(normalized or 'service', set())
    return f'background-color: {color};'


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


def _build_upcoming_item(subscription, index, today, service_color_map):
    effective_cost = subscription.user_cost if subscription.is_shared else subscription.cost
    renewal_date = _effective_renewal_date(subscription, today)
    return {
        'is_placeholder': False,
        'bg_class': '',
        'bg_style': _service_bg_style(subscription.service_name, service_color_map),
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


def _build_subscription_panel_item(subscription, index, service_color_map):
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
        'bg_style': _service_bg_style(subscription.service_name, service_color_map),
        'title': subscription.service_name,
        'subtitle': f"{_format_money(_monthly_cost(subscription), subscription.currency)}/monthly",
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
        'monthly': '1 month',
        'yearly': '1 year',
    }
    return mapping.get(subscription.billing_cycle, '1 month')


def _build_active_item(subscription, index, service_color_map):
    effective_cost = subscription.user_cost if subscription.is_shared else subscription.cost
    card_last4 = subscription.card.last4 if subscription.card else None
    return {
        'is_placeholder': False,
        'bg_class': '',
        'bg_style': _service_bg_style(subscription.service_name, service_color_map),
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
        'is_placeholder': False,
        'bg_class': '',
        'swatch_style': _service_bg_style(transaction.service_name_snapshot, service_color_map),
        'title': transaction.service_name_snapshot,
        'timestamp': timezone.localtime(transaction.charged_at).strftime('%b %d, %I:%M %p'),
        'amount': f"-{_format_money(transaction.amount, transaction.currency)}",
    }


def build_dashboard_view_model(user, today=None, scope='personal'):
    today = today or timezone.localdate()
    next_30_days = today + timedelta(days=30)
    scope = _normalize_dashboard_scope(scope)

    user_subs, scope = _subscriptions_for_scope(user, scope)

    if scope == 'teams':
        view_all_url = reverse('accounts:teams_overview')
    else:
        view_all_url = _renewal_view_all_url()

    active_subs_qs = user_subs.filter(status='active')
    active_subs = sorted(
        list(active_subs_qs),
        key=lambda sub: (
            _effective_renewal_date(sub, today) or date.max,
            (sub.service_name or '').lower(),
        ),
    )
    paused_subs = user_subs.filter(status='paused')
    cancelled_subs = user_subs.filter(status='cancelled')
    paused_subs_list = list(paused_subs)
    cancelled_subs_list = list(cancelled_subs)
    shared_subs = active_subs_qs.filter(is_shared=True)
    upcoming_renewals = []
    for sub in active_subs:
        renewal_date = _effective_renewal_date(sub, today)
        if renewal_date and today <= renewal_date <= next_30_days:
            upcoming_renewals.append(sub)

    monthly_spend_by_currency = _monthly_spend_by_currency(active_subs)
    upcoming_total_by_currency = {}
    for sub in upcoming_renewals:
        currency = (sub.currency or 'USD').upper()
        charge_amount = sub.user_cost if sub.is_shared else sub.cost
        upcoming_total_by_currency[currency] = (
            upcoming_total_by_currency.get(currency, Decimal('0.00')) + charge_amount
        )
    total_subscriptions_balance_by_currency = {}
    for sub in active_subs + paused_subs_list + cancelled_subs_list:
        currency = (sub.currency or 'USD').upper()
        total_subscriptions_balance_by_currency[currency] = (
            total_subscriptions_balance_by_currency.get(currency, Decimal('0.00'))
            + _monthly_cost(sub)
        )

    monthly_spend = monthly_spend_by_currency.get('USD', Decimal('0.00'))
    yearly_spend = monthly_spend * Decimal('12')
    active_count = len(active_subs)
    usd_active_count = sum(
        1 for sub in active_subs if (sub.currency or 'USD').upper() == 'USD'
    )
    paused_count = len(paused_subs_list)
    cancelled_count = len(cancelled_subs_list)
    shared_count = shared_subs.count()
    avg_monthly_spend = (
        monthly_spend / Decimal(usd_active_count)
        if usd_active_count
        else Decimal('0.00')
    )

    recent_transactions_qs = list(
        Transaction.objects.filter(user=user)
        .select_related('subscription')
        .order_by('-charged_at')[:2]
    )
    service_color_map = _build_service_color_map(active_subs, recent_transactions_qs)

    upcoming_items = [
        _build_upcoming_item(sub, index, today, service_color_map)
        for index, sub in enumerate(upcoming_renewals)
    ]
    subscription_panel_items = [
        _build_subscription_panel_item(sub, index, service_color_map)
        for index, sub in enumerate(active_subs[:3])
    ]
    active_panel_items = [
        _build_active_item(sub, index, service_color_map)
        for index, sub in enumerate(active_subs)
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

    next_renewal = upcoming_renewals[0] if upcoming_renewals else None
    next_renewal_date = _effective_renewal_date(next_renewal, today) if next_renewal else None
    chip_date = next_renewal_date.strftime('%m/%d') if next_renewal_date else '--/--'
    balance_trend = _build_balance_trend_points(user, today, window_days=30)
    balance_snapshot = _build_balance_snapshot(user, monthly_spend_by_currency)
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
        'stats_total_active': active_count,
        'stats_total_paused': paused_count,
        'stats_total_cancelled': cancelled_count,
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
