from collections.abc import Mapping

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .cards_state import (
    CARD_BRANDS,
    CARD_THEMES,
    apply_modal_query_state,
    build_cards_page_state,
    normalize_card_brand,
    normalize_card_theme,
    normalize_primary_cards_for_user,
    parse_boolean,
    set_primary_card_for_user,
)
from .forms import CardForm
from .models import Card, Subscription


def _card_state_response(user, *, status=200):
    return Response({"ok": True, "state": build_cards_page_state(user)}, status=status)


def _card_error_response(*, errors=None, message=None, status=400):
    payload = {"ok": False}
    if message:
        payload["message"] = message
    if errors:
        payload["errors"] = errors
    return Response(payload, status=status)


def _text(payload, key):
    value = payload.get(key)
    return value.strip() if isinstance(value, str) else ""


def _validate_card_payload(payload):
    nickname = _text(payload, "nickname")
    last4 = _text(payload, "last4")
    raw_brand = _text(payload, "brand").lower()
    raw_theme = _text(payload, "theme").lower()
    brand = normalize_card_brand(raw_brand)
    theme = normalize_card_theme(raw_theme)
    is_primary = parse_boolean(payload.get("isPrimary"))

    errors = {}
    if not nickname:
        errors["nickname"] = "Card nickname is required."
    elif len(nickname) > 50:
        errors["nickname"] = "Nickname must be 50 characters or fewer."

    if not last4:
        errors["last4"] = "Last 4 digits are required."
    elif len(last4) != 4 or not (last4.isascii() and last4.isdecimal()):
        errors["last4"] = "Must be exactly 4 digits."

    if raw_brand not in CARD_BRANDS:
        errors["brand"] = "Invalid card brand."

    if raw_theme not in CARD_THEMES:
        errors["theme"] = "Invalid card theme."

    return {
        "nickname": nickname,
        "last4": last4,
        "brand": brand,
        "theme": theme,
        "is_primary": is_primary,
        "errors": errors,
    }


def _resolve_replacement_card_id(user, raw_value):
    if raw_value in (None, ""):
        return None, None

    if isinstance(raw_value, bool) or not isinstance(raw_value, (str, int)):
        return None, "Invalid destination card."
    try:
        move_card_id = int(raw_value)
    except ValueError:
        return None, "Invalid destination card."

    card = Card.objects.filter(user=user, pk=move_card_id).first()
    if not card:
        return None, "Destination card not found."
    return card, None


@login_required
def card_list(request):
    state = build_cards_page_state(request.user)
    apply_modal_query_state(state, request.GET)
    return render(
        request,
        "subscriptions/cards.html",
        {
            "cards_initial_state": state,
            "legacy_title": "Cards",
        },
    )

@login_required
def card_create(request):
    if request.method == "GET":
        return redirect(f"{reverse('subscriptions:card_list')}?modal=add")

    if request.method == 'POST':
        form = CardForm(request.POST)
        if form.is_valid():
            card = form.save(commit=False)
            card.user = request.user
            card.brand = (card.brand or "").strip() or None
            card.theme = normalize_card_theme(getattr(card, "theme", None))
            card.is_primary = False
            card.save()
            normalize_primary_cards_for_user(request.user)
            return redirect('subscriptions:card_list')
    else:
        form = CardForm()
    return render(request, 'subscriptions/card_form.html', {'form': form, 'title': 'Add Card'})

@login_required
def card_update(request, pk):
    card = get_object_or_404(Card, pk=pk, user=request.user)
    if request.method == "GET":
        return redirect(f"{reverse('subscriptions:card_list')}?modal=edit&card={card.pk}")

    if request.method == 'POST':
        form = CardForm(request.POST, instance=card)
        if form.is_valid():
            updated_card = form.save(commit=False)
            updated_card.brand = (updated_card.brand or "").strip() or None
            updated_card.theme = normalize_card_theme(getattr(updated_card, "theme", None))
            updated_card.save()
            normalize_primary_cards_for_user(request.user)
            return redirect('subscriptions:card_list')
    else:
        form = CardForm(instance=card)
    return render(request, 'subscriptions/card_form.html', {'form': form, 'title': 'Edit Card'})

@login_required
def card_delete(request, pk):
    card = get_object_or_404(Card, pk=pk, user=request.user)
    if request.method == "GET":
        return redirect(f"{reverse('subscriptions:card_list')}?modal=delete&card={card.pk}")

    if request.method == 'POST':
        with transaction.atomic():
            Subscription.objects.filter(user=request.user, card=card).update(card=None)
            card.delete()
            normalize_primary_cards_for_user(request.user)
        return redirect('subscriptions:card_list')
    return JsonResponse({"ok": False, "message": "Method not allowed."}, status=405)


def _cards_state(request):
    return _card_state_response(request.user)


def _cards_create(request):

    if not isinstance(request.data, Mapping):
        return _card_error_response(message="Expected a JSON object.")
    data = request.data
    parsed = _validate_card_payload(data)
    if parsed["errors"]:
        return _card_error_response(errors=parsed["errors"], status=400)

    with transaction.atomic():
        card = Card.objects.create(
            user=request.user,
            nickname=parsed["nickname"],
            last4=parsed["last4"],
            brand=parsed["brand"],
            theme=parsed["theme"],
            is_primary=False,
        )

        has_other_cards = Card.objects.filter(user=request.user).exclude(pk=card.pk).exists()
        if parsed["is_primary"] or not has_other_cards:
            set_primary_card_for_user(user=request.user, card=card)
        else:
            normalize_primary_cards_for_user(request.user)

    return _card_state_response(request.user, status=201)


def _cards_update(request, pk):

    card = get_object_or_404(Card, pk=pk, user=request.user)
    if not isinstance(request.data, Mapping):
        return _card_error_response(message="Expected a JSON object.")
    data = request.data
    parsed = _validate_card_payload(data)
    if parsed["errors"]:
        return _card_error_response(errors=parsed["errors"], status=400)

    with transaction.atomic():
        card.nickname = parsed["nickname"]
        card.last4 = parsed["last4"]
        card.brand = parsed["brand"]
        card.theme = parsed["theme"]
        card.is_primary = False
        card.save()

        if parsed["is_primary"]:
            set_primary_card_for_user(user=request.user, card=card)
        else:
            normalize_primary_cards_for_user(request.user)

    return _card_state_response(request.user)


def _cards_set_primary(request, pk):

    card = get_object_or_404(Card, pk=pk, user=request.user)
    with transaction.atomic():
        set_primary_card_for_user(user=request.user, card=card)
        normalize_primary_cards_for_user(request.user)
    return _card_state_response(request.user)


def _cards_delete(request, pk):

    card = get_object_or_404(Card, pk=pk, user=request.user)
    if not isinstance(request.data, Mapping):
        return _card_error_response(message="Expected a JSON object.")
    data = request.data
    move_card, move_error = _resolve_replacement_card_id(request.user, data.get("move_to_card_id"))
    if move_error:
        return _card_error_response(errors={"move_to_card_id": move_error}, status=400)

    if move_card and move_card.pk == card.pk:
        return _card_error_response(
            errors={"move_to_card_id": "Cannot move subscriptions to the same card."},
            status=400,
        )

    with transaction.atomic():
        if move_card:
            Subscription.objects.filter(card=card).update(card=move_card)

        card.delete()
        normalize_primary_cards_for_user(request.user)

    return _card_state_response(request.user)


cards_api_state = api_view(["GET"])(_cards_state)
cards_api_create = api_view(["POST"])(_cards_create)
cards_api_update = api_view(["POST"])(_cards_update)
cards_api_set_primary = api_view(["POST"])(_cards_set_primary)
cards_api_delete = api_view(["POST"])(_cards_delete)


@api_view(["GET", "POST"])
def cards_collection(request):
    if request.method == "POST":
        return _cards_create(request)
    return _cards_state(request)


@api_view(["PUT", "DELETE"])
def card_detail(request, pk):
    if request.method == "DELETE":
        return _cards_delete(request, pk)
    return _cards_update(request, pk)
