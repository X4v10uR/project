import hashlib

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from dashboard.constants import CARD_COLOR_PALETTE, SERVICE_COLOR_PREFERENCES

from .money import monthly_equivalent
from .models import Card, Subscription
from .color_utils import normalize_subscription_display_color


CARD_BRANDS = ("visa", "mastercard", "amex", "discover", "jcb")
CARD_THEMES = (
    Card.THEME_DARK,
    Card.THEME_NAVY,
    Card.THEME_FOREST,
    Card.THEME_PLUM,
    Card.THEME_ROSE,
)

BRAND_ALIASES = {
    "american express": "amex",
    "master card": "mastercard",
}

SERVICE_ICON_BG_PREFERENCES = {
    "spotify": "#1DB954",
    "netflix": "#E50914",
    "youtube premium": "#FF0000",
    "youtube": "#FF0000",
    "adobe creative cloud": "#3A3A8A",
    "creative cloud": "#3A3A8A",
    "apple tv": "#111111",
    "disney+": "#0D1B7E",
}


def parse_boolean(raw_value):
    if isinstance(raw_value, bool):
        return raw_value
    if isinstance(raw_value, str):
        return raw_value.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(raw_value, int):
        return raw_value == 1
    return False


def normalize_card_brand(raw_brand):
    if not raw_brand:
        return "visa"

    normalized = str(raw_brand).strip().lower()
    normalized = BRAND_ALIASES.get(normalized, normalized)
    if normalized not in CARD_BRANDS:
        return "visa"
    return normalized


def normalize_card_theme(raw_theme):
    if not raw_theme:
        return Card.THEME_DARK

    normalized = str(raw_theme).strip().lower()
    if normalized not in CARD_THEMES:
        return Card.THEME_DARK
    return normalized


def normalize_primary_cards_for_user(user):
    cards = Card.objects.filter(user=user).order_by("-created_at", "-id")
    primary = cards.filter(is_primary=True).first()
    if primary:
        return primary
    card = cards.first()
    return set_primary_card_for_user(user=user, card=card) if card else None


@transaction.atomic
def set_primary_card_for_user(*, user, card):
    Card.objects.filter(user=user, is_primary=True).exclude(pk=card.pk).update(is_primary=False)
    Card.objects.filter(pk=card.pk, is_primary=False).update(is_primary=True)
    card.is_primary = True
    return card


def _stable_bucket(value):
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _service_color(subscription):
    custom_color = normalize_subscription_display_color(
        getattr(subscription, "display_color", "")
    )
    if custom_color:
        return custom_color

    normalized = (subscription.service_name or "").strip().lower()
    preferred = SERVICE_COLOR_PREFERENCES.get(normalized)
    if preferred:
        return preferred

    if not CARD_COLOR_PALETTE:
        return "#AFC0DE"

    index = _stable_bucket(normalized or "subscription") % len(CARD_COLOR_PALETTE)
    return CARD_COLOR_PALETTE[index]


def _service_icon_bg(service_name, fallback_color):
    normalized = (service_name or "").strip().lower()
    return SERVICE_ICON_BG_PREFERENCES.get(normalized, fallback_color)


def _service_icon_label(service_name):
    name = (service_name or "").strip()
    if not name:
        return "S"

    if len(name) > 1 and name[1] == "+":
        return name[:2]

    tokens = [token for token in name.split(" ") if token]
    if len(tokens) >= 2:
        return f"{tokens[0][0]}{tokens[1][0]}".upper()
    return name[0].upper()


def _format_display_date(raw_date):
    if not raw_date:
        return "No date set"
    return f"{raw_date.strftime('%b')} {raw_date.day}, {raw_date.year}"


def build_card_options(user):
    cards = list(Card.objects.filter(user=user).order_by("-created_at", "-id"))
    primary = next((card for card in cards if card.is_primary), cards[0] if cards else None)
    return [
        {
            "id": str(card.pk),
            "nickname": card.nickname,
            "last4": card.last4,
            "brand": normalize_card_brand(card.brand),
            "isPrimary": card == primary,
            "theme": normalize_card_theme(card.theme),
        }
        for card in cards
    ]


def build_cards_page_state(user):
    today = timezone.localdate()
    subscriptions = (
        Subscription.objects.filter(status="active", card__user=user)
        .filter(Q(user=user, team__isnull=True) | Q(team__memberships__user=user))
        .prefetch_related("price_changes", "participants")
        .order_by("renewal_date", "service_name")
    )

    subscriptions_payload = []
    for subscription in subscriptions:
        amount = subscription.share_on(today) if subscription.bills_on(today) else 0
        monthly_price = monthly_equivalent(amount, subscription.billing_cycle)
        color = _service_color(subscription)
        days_left = 0
        if subscription.renewal_date:
            days_left = max((subscription.renewal_date - today).days, 0)

        subscriptions_payload.append(
            {
                "id": f"s{subscription.pk}",
                "name": subscription.service_name,
                "teamId": subscription.team_id,
                "monthlyPrice": float(monthly_price),
                "currency": subscription.currency,
                "billingCycle": subscription.billing_cycle,
                "cardId": str(subscription.card_id),
                "color": color,
                "iconBg": _service_icon_bg(subscription.service_name, color),
                "iconLabel": _service_icon_label(subscription.service_name),
                "nextBillingDate": _format_display_date(subscription.renewal_date),
                "daysLeft": days_left,
                "plan": subscription.plan_name or subscription.billing_cycle.title(),
            }
        )

    return {
        "cards": build_card_options(user),
        "subscriptions": subscriptions_payload,
        "selectedCardId": None,
        "search": "",
        "addModalOpen": False,
        "editCardId": None,
        "deleteCardId": None,
    }


def apply_modal_query_state(state, query_params):
    modal = (query_params.get("modal") or "").strip().lower()
    card_id = (query_params.get("card") or "").strip()
    existing_card_ids = {card["id"] for card in state["cards"]}

    if modal == "add":
        state["addModalOpen"] = True
        return state

    if modal == "edit" and card_id in existing_card_ids:
        state["addModalOpen"] = True
        state["editCardId"] = card_id
        state["selectedCardId"] = card_id
        return state

    if modal == "delete" and card_id in existing_card_ids:
        state["deleteCardId"] = card_id
        state["selectedCardId"] = card_id
        return state

    return state
