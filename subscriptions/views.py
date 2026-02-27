from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from decimal import Decimal, InvalidOperation
from datetime import timedelta
import csv
import json

from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from django.urls import reverse
from .models import Subscription, ReminderOffset, Card, SubscriptionParticipant
from .forms import SubscriptionForm, CardForm
from django.http import HttpResponse, JsonResponse
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

CATEGORY_SUGGESTIONS = [
    "Streaming",
    "Music",
    "Video",
    "Software",
    "Utilities",
    "Cloud",
    "Gaming",
    "Productivity",
    "Education",
    "News",
]


def _parse_participants_data(request):
    participant_names = request.POST.getlist('participant_name')
    participant_shares = request.POST.getlist('participant_share')

    participants_data = []
    for i, raw_name in enumerate(participant_names):
        name = raw_name.strip()
        if not name:
            continue

        raw_share = '0'
        if i < len(participant_shares):
            raw_share = (participant_shares[i] or '0').strip()

        try:
            share = Decimal(raw_share or '0')
        except (InvalidOperation, TypeError):
            return None, 'Participant shares must be valid numbers.'

        if share < 0:
            return None, 'Participant shares cannot be negative.'

        participants_data.append({'name': name, 'share': share})

    if not participants_data:
        return None, 'Please add at least one participant for shared subscriptions.'

    return participants_data, None


def _parse_reminder_offsets(raw_offsets):
    valid_offsets = set()
    for offset_days in raw_offsets:
        try:
            days = int(offset_days)
        except (ValueError, TypeError):
            continue

        if 1 <= days <= 30:
            valid_offsets.add(days)
    return sorted(valid_offsets)


def _build_subscription_prefill(get_params):
    allowed = {}

    service_name = (get_params.get('service_name') or '').strip()
    category = (get_params.get('category') or '').strip()
    plan_name = (get_params.get('plan_name') or '').strip()
    billing_cycle = (get_params.get('billing_cycle') or '').strip()

    if service_name:
        allowed['service_name'] = service_name[:100]
    if category:
        allowed['category'] = category[:50]
    if plan_name:
        allowed['plan_name'] = plan_name[:100]
    if billing_cycle in dict(Subscription.BILLING_CYCLE_CHOICES):
        allowed['billing_cycle'] = billing_cycle

    return allowed


def _is_truthy(raw_value):
    return raw_value in (True, "True", "true", "1", 1, "on")


def _format_date_input(raw_value):
    if not raw_value:
        return ""
    if hasattr(raw_value, "strftime"):
        return raw_value.strftime("%Y-%m-%d")
    return str(raw_value)


def _format_time_input(raw_value):
    if not raw_value:
        return ""
    if hasattr(raw_value, "strftime"):
        return raw_value.strftime("%H:%M")
    return str(raw_value)[:5]


def _string_value(raw_value):
    if raw_value is None:
        return ""
    return str(raw_value)


def _build_participant_seed(*, subscription=None, post_data=None):
    if post_data is not None:
        participant_names = post_data.getlist("participant_name")
        participant_shares = post_data.getlist("participant_share")

        seed = []
        for idx, raw_name in enumerate(participant_names):
            raw_share = ""
            if idx < len(participant_shares):
                raw_share = participant_shares[idx]

            name = (raw_name or "").strip()
            share = (raw_share or "").strip()
            if not name and not share:
                continue
            seed.append({"name": name, "share": share})
        return seed

    if subscription and subscription.pk:
        return [
            {
                "name": participant.name,
                "share": _string_value(participant.share_amount),
            }
            for participant in subscription.participants.all()
        ]

    return []


def _build_reminder_seed(*, subscription=None, post_data=None):
    if post_data is not None:
        return _parse_reminder_offsets(post_data.getlist("reminder_offsets"))

    if subscription and subscription.pk:
        return list(
            subscription.offsets.order_by("days_before").values_list("days_before", flat=True)
        )

    return []


def _sync_reminder_offsets(subscription, reminder_offsets):
    desired_offsets = sorted(set(reminder_offsets))
    existing_offsets = set(
        subscription.offsets.values_list("days_before", flat=True)
    )

    to_remove = existing_offsets - set(desired_offsets)
    if to_remove:
        subscription.offsets.filter(days_before__in=to_remove).delete()

    to_add = [
        ReminderOffset(subscription=subscription, days_before=days)
        for days in desired_offsets
        if days not in existing_offsets
    ]
    if to_add:
        ReminderOffset.objects.bulk_create(to_add)


def _build_subscription_form_context(request, form, title, *, subscription=None):
    post_data = request.POST if request.method == "POST" else None
    is_edit_mode = bool(subscription and subscription.pk)
    instance = subscription if is_edit_mode else form.instance

    if form.is_bound:
        is_shared_selected = _is_truthy(form.data.get("is_shared"))
        split_type_selected = form.data.get("split_type") or "equal"
        status_selected = form.data.get("status") or "active"
        reminders_enabled_selected = _is_truthy(form.data.get("reminders_enabled"))
        selected_card_id = _string_value(form.data.get("card"))
    else:
        is_shared_selected = bool(getattr(instance, "is_shared", False))
        split_type_selected = getattr(instance, "split_type", None) or "equal"
        status_selected = getattr(instance, "status", None) or "active"
        reminders_enabled_selected = bool(
            getattr(instance, "reminders_enabled", True)
        )
        selected_card_id = _string_value(getattr(instance, "card_id", ""))

    service_name_value = form.data.get("service_name") if form.is_bound else form.initial.get("service_name", getattr(instance, "service_name", ""))
    plan_name_value = form.data.get("plan_name") if form.is_bound else form.initial.get("plan_name", getattr(instance, "plan_name", ""))
    category_value = form.data.get("category") if form.is_bound else form.initial.get("category", getattr(instance, "category", ""))
    billing_cycle_value = form.data.get("billing_cycle") if form.is_bound else form.initial.get("billing_cycle", getattr(instance, "billing_cycle", ""))
    cost_value = form.data.get("cost") if form.is_bound else form.initial.get("cost", getattr(instance, "cost", ""))
    currency_value = form.data.get("currency") if form.is_bound else form.initial.get("currency", getattr(instance, "currency", "USD"))
    start_date_raw = form.data.get("start_date") if form.is_bound else form.initial.get("start_date", getattr(instance, "start_date", None))
    renewal_time_raw = form.data.get("renewal_time") if form.is_bound else form.initial.get("renewal_time", getattr(instance, "renewal_time", None))
    account_email_value = form.data.get("account_email") if form.is_bound else form.initial.get("account_email", getattr(instance, "account_email", ""))
    notes_value = form.data.get("notes") if form.is_bound else form.initial.get("notes", getattr(instance, "notes", ""))

    context = {
        "form": form,
        "title": title,
        "is_edit_mode": is_edit_mode,
        "is_shared_selected": is_shared_selected,
        "split_type_selected": split_type_selected,
        "status_selected": status_selected,
        "reminders_enabled_selected": reminders_enabled_selected,
        "selected_card_id": selected_card_id,
        "service_name_value": _string_value(service_name_value),
        "plan_name_value": _string_value(plan_name_value),
        "category_value": _string_value(category_value),
        "billing_cycle_value": _string_value(billing_cycle_value),
        "cost_value": _string_value(cost_value),
        "currency_value": _string_value(currency_value),
        "start_date_value": _format_date_input(start_date_raw),
        "renewal_time_value": _format_time_input(renewal_time_raw),
        "account_email_value": _string_value(account_email_value),
        "notes_value": _string_value(notes_value),
        "participant_seed": _build_participant_seed(
            subscription=subscription, post_data=post_data
        ),
        "reminder_seed": _build_reminder_seed(
            subscription=subscription, post_data=post_data
        ),
        "category_suggestions": CATEGORY_SUGGESTIONS,
    }
    return context


def _render_subscription_form(request, form, title, *, subscription=None):
    return render(
        request,
        "subscriptions/form.html",
        _build_subscription_form_context(
            request, form, title, subscription=subscription
        ),
    )


def _json_data(request):
    if not request.body:
        return {}

    try:
        return json.loads(request.body.decode("utf-8"))
    except (TypeError, json.JSONDecodeError):
        return {}


def _cards_state_response(user, *, status=200):
    return JsonResponse({"ok": True, "state": build_cards_page_state(user)}, status=status)


def _cards_error_response(*, errors=None, message=None, status=400):
    payload = {"ok": False}
    if message:
        payload["message"] = message
    if errors:
        payload["errors"] = errors
    return JsonResponse(payload, status=status)


def _validate_card_payload(payload):
    nickname = (payload.get("nickname") or "").strip()
    last4 = (payload.get("last4") or "").strip()
    raw_brand = (payload.get("brand") or "").strip().lower()
    raw_theme = (payload.get("theme") or "").strip().lower()
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
    elif len(last4) != 4 or not last4.isdigit():
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


def _parse_move_card_id(user, raw_value):
    if raw_value in (None, ""):
        return None, None

    try:
        move_card_id = int(raw_value)
    except (TypeError, ValueError):
        return None, "Invalid destination card."

    card = Card.objects.filter(user=user, pk=move_card_id).first()
    if not card:
        return None, "Destination card not found."
    return card, None

@login_required
def card_list(request):
    normalize_primary_cards_for_user(request.user)
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
    return _cards_error_response(message="Method not allowed.", status=405)


@login_required
def cards_api_state(request):
    if request.method != "GET":
        return _cards_error_response(message="GET required.", status=405)
    normalize_primary_cards_for_user(request.user)
    return _cards_state_response(request.user)


@login_required
def cards_api_create(request):
    if request.method != "POST":
        return _cards_error_response(message="POST required.", status=405)

    data = _json_data(request)
    parsed = _validate_card_payload(data)
    if parsed["errors"]:
        return _cards_error_response(errors=parsed["errors"], status=400)

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

    return _cards_state_response(request.user, status=201)


@login_required
def cards_api_update(request, pk):
    if request.method != "POST":
        return _cards_error_response(message="POST required.", status=405)

    card = get_object_or_404(Card, pk=pk, user=request.user)
    data = _json_data(request)
    parsed = _validate_card_payload(data)
    if parsed["errors"]:
        return _cards_error_response(errors=parsed["errors"], status=400)

    with transaction.atomic():
        was_primary = card.is_primary
        card.nickname = parsed["nickname"]
        card.last4 = parsed["last4"]
        card.brand = parsed["brand"]
        card.theme = parsed["theme"]
        card.is_primary = False
        card.save()

        if parsed["is_primary"]:
            set_primary_card_for_user(user=request.user, card=card)
        elif was_primary:
            normalize_primary_cards_for_user(request.user)
        else:
            normalize_primary_cards_for_user(request.user)

    return _cards_state_response(request.user)


@login_required
def cards_api_set_primary(request, pk):
    if request.method != "POST":
        return _cards_error_response(message="POST required.", status=405)

    card = get_object_or_404(Card, pk=pk, user=request.user)
    with transaction.atomic():
        set_primary_card_for_user(user=request.user, card=card)
        normalize_primary_cards_for_user(request.user)
    return _cards_state_response(request.user)


@login_required
def cards_api_delete(request, pk):
    if request.method != "POST":
        return _cards_error_response(message="POST required.", status=405)

    card = get_object_or_404(Card, pk=pk, user=request.user)
    data = _json_data(request)
    move_card, move_error = _parse_move_card_id(request.user, data.get("move_to_card_id"))
    if move_error:
        return _cards_error_response(errors={"move_to_card_id": move_error}, status=400)

    if move_card and move_card.pk == card.pk:
        return _cards_error_response(
            errors={"move_to_card_id": "Cannot move subscriptions to the same card."},
            status=400,
        )

    with transaction.atomic():
        if move_card:
            Subscription.objects.filter(user=request.user, card=card).update(card=move_card)
        else:
            Subscription.objects.filter(user=request.user, card=card).update(card=None)

        card.delete()
        normalize_primary_cards_for_user(request.user)

    return _cards_state_response(request.user)


def _build_subscription_list_state(request):
    query = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')
    cycle_filter = request.GET.get('cycle', '')
    shared_filter = request.GET.get('shared', '')
    due_within = request.GET.get('due_within', '')
    sort_by = request.GET.get('sort', 'renewal_date')

    subscriptions = Subscription.objects.filter(user=request.user).annotate(
        participant_count=Count('participants')
    )

    if query:
        subscriptions = subscriptions.filter(service_name__icontains=query)
    if status_filter:
        subscriptions = subscriptions.filter(status=status_filter)
    if cycle_filter:
        subscriptions = subscriptions.filter(billing_cycle=cycle_filter)
    if shared_filter == 'true':
        subscriptions = subscriptions.filter(is_shared=True)

    due_within_days = None
    if due_within:
        try:
            parsed_due_within = int(due_within)
            if 1 <= parsed_due_within <= 365:
                due_within_days = parsed_due_within
        except (TypeError, ValueError):
            due_within_days = None

    if due_within_days is not None:
        today = timezone.localdate()
        subscriptions = subscriptions.filter(
            renewal_date__range=[today, today + timedelta(days=due_within_days)]
        )

    if sort_by in ['cost', 'renewal_date', 'service_name']:
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


@login_required
def subscription_list(request):
    subscriptions, filters = _build_subscription_list_state(request)
    return render(
        request,
        'subscriptions/list.html',
        {
            'subscriptions': subscriptions,
            **filters,
        },
    )


@login_required
def subscription_export_csv(request):
    subscriptions, _ = _build_subscription_list_state(request)
    subscriptions = subscriptions.prefetch_related('participants')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = (
        f'attachment; filename="subscriptions-{timezone.localdate().isoformat()}.csv"'
    )

    writer = csv.writer(response)
    writer.writerow(
        [
            'Service Name',
            'Plan Name',
            'Category',
            'Billing Cycle',
            'Status',
            'Is Shared',
            'Participants',
            'Account Email',
            'Currency',
            'Total Cost',
            'Your Cost',
            'Start Date',
            'Renewal Date',
            'Renewal Time',
            'Notes',
        ]
    )

    for subscription in subscriptions:
        participant_names = ', '.join(
            subscription.participants.order_by('name').values_list('name', flat=True)
        )
        writer.writerow(
            [
                subscription.service_name,
                subscription.plan_name or '',
                subscription.category,
                subscription.billing_cycle,
                subscription.status,
                'Yes' if subscription.is_shared else 'No',
                participant_names,
                subscription.account_email or '',
                subscription.currency,
                str(subscription.cost),
                str(subscription.user_cost),
                subscription.start_date.isoformat() if subscription.start_date else '',
                subscription.renewal_date.isoformat()
                if subscription.renewal_date
                else '',
                subscription.renewal_time.strftime('%H:%M')
                if subscription.renewal_time
                else '',
                subscription.notes or '',
            ]
        )

    return response

@login_required
def subscription_create(request):
    if request.method == 'POST':
        form = SubscriptionForm(request.POST, user=request.user)
        if form.is_valid():
            subscription = form.save(commit=False)
            subscription.user = request.user
            reminder_offsets = _parse_reminder_offsets(
                request.POST.getlist("reminder_offsets")
            )
            
            # Handle shared subscription logic
            is_shared = form.cleaned_data.get('is_shared')
            if is_shared:
                split_type = form.cleaned_data.get('split_type')
                participants_data, participants_error = _parse_participants_data(request)
                if participants_error:
                    form.add_error(None, participants_error)
                    return _render_subscription_form(
                        request, form, 'Add Subscription'
                    )

                total_participants = len(participants_data) + 1  # +1 for user
                participants_to_create = []

                if split_type == 'equal':
                    share_per_person = subscription.cost / Decimal(total_participants)
                    subscription.user_cost = share_per_person
                    participants_to_create = [
                        SubscriptionParticipant(
                            subscription=subscription,
                            name=p_data['name'],
                            share_amount=share_per_person
                        )
                        for p_data in participants_data
                    ]
                else:  # Custom split
                    total_others_share = sum((p['share'] for p in participants_data), Decimal('0'))
                    subscription.user_cost = subscription.cost - total_others_share

                    if subscription.user_cost < 0:
                        form.add_error(None, 'The sum of participant shares exceeds the total cost.')
                        return _render_subscription_form(
                            request, form, 'Add Subscription'
                        )

                    participants_to_create = [
                        SubscriptionParticipant(
                            subscription=subscription,
                            name=p_data['name'],
                            share_amount=p_data['share']
                        )
                        for p_data in participants_data
                    ]

                with transaction.atomic():
                    subscription.save()  # Save with user_cost
                    SubscriptionParticipant.objects.bulk_create(participants_to_create)
                    _sync_reminder_offsets(subscription, reminder_offsets)
                
            else:
                subscription.user_cost = subscription.cost
                with transaction.atomic():
                    subscription.save()
                    _sync_reminder_offsets(subscription, reminder_offsets)
            
            return redirect('subscriptions:list')
    else:
        initial = _build_subscription_prefill(request.GET)
        form = SubscriptionForm(user=request.user, initial=initial)
    return _render_subscription_form(request, form, 'Add Subscription')

@login_required
def subscription_update(request, pk):
    subscription = get_object_or_404(Subscription, pk=pk, user=request.user)
    if request.method == 'POST':
        form = SubscriptionForm(request.POST, instance=subscription, user=request.user)
        if form.is_valid():
            subscription = form.save(commit=False)
            reminder_offsets = _parse_reminder_offsets(
                request.POST.getlist("reminder_offsets")
            )
            
            # Handle shared subscription logic
            is_shared = form.cleaned_data.get('is_shared')
            
            if is_shared:
                split_type = form.cleaned_data.get('split_type')
                participants_data, participants_error = _parse_participants_data(request)
                if participants_error:
                    form.add_error(None, participants_error)
                    return _render_subscription_form(
                        request,
                        form,
                        'Edit Subscription',
                        subscription=subscription,
                    )

                total_participants = len(participants_data) + 1  # +1 for user

                if split_type == 'equal':
                    share_per_person = subscription.cost / Decimal(total_participants)
                    subscription.user_cost = share_per_person
                    participants_to_create = [
                        SubscriptionParticipant(
                            subscription=subscription,
                            name=p_data['name'],
                            share_amount=share_per_person
                        )
                        for p_data in participants_data
                    ]
                else:  # Custom split
                    total_others_share = sum((p['share'] for p in participants_data), Decimal('0'))
                    subscription.user_cost = subscription.cost - total_others_share

                    if subscription.user_cost < 0:
                        form.add_error(None, 'The sum of participant shares exceeds the total cost.')
                        return _render_subscription_form(
                            request,
                            form,
                            'Edit Subscription',
                            subscription=subscription,
                        )

                    participants_to_create = [
                        SubscriptionParticipant(
                            subscription=subscription,
                            name=p_data['name'],
                            share_amount=p_data['share']
                        )
                        for p_data in participants_data
                    ]

                with transaction.atomic():
                    subscription.save()
                    # Replace participant list only after all validations pass.
                    subscription.participants.all().delete()
                    SubscriptionParticipant.objects.bulk_create(participants_to_create)
                    _sync_reminder_offsets(subscription, reminder_offsets)
            else:
                subscription.user_cost = subscription.cost
                with transaction.atomic():
                    subscription.save()
                    subscription.participants.all().delete()  # Cleanup if switched from Shared to Solo
                    _sync_reminder_offsets(subscription, reminder_offsets)

            return redirect('subscriptions:list')
    else:
        form = SubscriptionForm(instance=subscription, user=request.user)
    return _render_subscription_form(
        request,
        form,
        'Edit Subscription',
        subscription=subscription,
    )

@login_required
def subscription_delete(request, pk):
    subscription = get_object_or_404(Subscription, pk=pk, user=request.user)
    if request.method == 'POST':
        subscription.delete()
        return redirect('subscriptions:list')
    return render(request, 'subscriptions/confirm_delete.html', {'subscription': subscription})
@login_required
def delete_reminder_offset(request, pk):
    offset = get_object_or_404(ReminderOffset, pk=pk, subscription__user=request.user)
    subscription_id = offset.subscription.id
    if request.method == 'POST':
        offset.delete()
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'success'})
        return redirect('subscriptions:update', pk=subscription_id)
    return redirect('subscriptions:update', pk=subscription_id)

@login_required
def add_reminder_offset(request, pk):
    subscription = get_object_or_404(Subscription, pk=pk, user=request.user)
    if request.method == 'POST':
        days_before = request.POST.get('days_before')
        try:
            days_before_int = int(days_before)
        except (TypeError, ValueError):
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'message': 'days_before must be an integer'}, status=400)
            return redirect('subscriptions:update', pk=pk)

        if not 1 <= days_before_int <= 30:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'message': 'days_before must be between 1 and 30'}, status=400)
            return redirect('subscriptions:update', pk=pk)

        ReminderOffset.objects.get_or_create(subscription=subscription, days_before=days_before_int)
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'success'})
        return redirect('subscriptions:update', pk=pk)
    return redirect('subscriptions:update', pk=pk)

@login_required
def update_subscription_status(request, pk):
    """Update subscription status via AJAX"""
    subscription = get_object_or_404(Subscription, pk=pk, user=request.user)
    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status in ['active', 'paused', 'cancelled']:
            subscription.status = new_status
            subscription.save()
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'success', 'new_status': new_status})
            return redirect('subscriptions:list')
        return JsonResponse({'status': 'error', 'message': 'Invalid status'}, status=400)
    return JsonResponse({'status': 'error', 'message': 'POST required'}, status=405)

