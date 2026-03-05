import hashlib

from django.utils import timezone

from dashboard.constants import CARD_COLOR_PALETTE, SERVICE_COLOR_PREFERENCES

from .money import monthly_equivalent
from .models import Card, Subscription


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
    cards = list(Card.objects.filter(user=user).order_by("-created_at", "-id"))
    if not cards:
        return None

    primary_cards = [card for card in cards if card.is_primary]
    primary_card = primary_cards[0] if primary_cards else cards[0]

    Card.objects.filter(user=user).exclude(pk=primary_card.pk).update(is_primary=False)
    if not primary_card.is_primary:
        Card.objects.filter(pk=primary_card.pk).update(is_primary=True)
        primary_card.is_primary = True

    return primary_card


def set_primary_card_for_user(*, user, card):
    Card.objects.filter(user=user).exclude(pk=card.pk).update(is_primary=False)
    if not card.is_primary:
        Card.objects.filter(pk=card.pk).update(is_primary=True)
        card.is_primary = True
    return card


def _stable_bucket(value):
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _service_color(service_name):
    normalized = (service_name or "").strip().lower()
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


def _monthly_price(subscription):
    amount = subscription.user_cost if subscription.is_shared else subscription.cost
    return monthly_equivalent(amount, subscription.billing_cycle)


def _format_display_date(raw_date):
    if not raw_date:
        return "No date set"
    return f"{raw_date.strftime('%b')} {raw_date.day}, {raw_date.year}"


def build_cards_page_state(user):
    today = timezone.localdate()

    cards = list(Card.objects.filter(user=user).order_by("-created_at", "-id"))
    subscriptions = (
        Subscription.objects.filter(user=user, status="active", card__isnull=False)
        .select_related("card")
        .order_by("renewal_date", "service_name")
    )

    cards_payload = [
        {
            "id": str(card.pk),
            "nickname": card.nickname,
            "last4": card.last4,
            "brand": normalize_card_brand(card.brand),
            "isPrimary": bool(card.is_primary),
            "theme": normalize_card_theme(card.theme),
        }
        for card in cards
    ]

    subscriptions_payload = []
    for subscription in subscriptions:
        monthly_price = _monthly_price(subscription)
        color = _service_color(subscription.service_name)
        days_left = 0
        if subscription.renewal_date:
            days_left = max((subscription.renewal_date - today).days, 0)

        subscriptions_payload.append(
            {
                "id": f"s{subscription.pk}",
                "name": subscription.service_name,
                "monthlyPrice": float(monthly_price),
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
        "cards": cards_payload,
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
