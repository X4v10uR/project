import csv
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from accounts.models import Team, TeamMembership
from accounts.services import is_team_member, is_team_owner

from .color_utils import (
    LIGHT_SUBSCRIPTION_COLOR_PRESETS,
    normalize_subscription_display_color,
)
from .forms import SubscriptionForm
from .list_context import build_subscription_list_context, filter_personal_subscriptions
from .models import ReminderOffset, Subscription, SubscriptionParticipant, TeamSubscriptionRequest
from .notifications import create_notification, create_team_notifications
from .services import record_due_charge_for_subscription


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

CSV_FORMULA_PREFIXES = ('=', '+', '-', '@')

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


def _build_subscription_form_context(request, form, title, *, subscription=None, team_context=None):
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
    display_color_value = (
        form.data.get("display_color")
        if form.is_bound
        else form.initial.get("display_color", getattr(instance, "display_color", ""))
    )
    display_color_value = normalize_subscription_display_color(display_color_value)

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
        "display_color_value": display_color_value,
        "display_color_picker_value": (
            display_color_value or LIGHT_SUBSCRIPTION_COLOR_PRESETS[0]
        ),
        "subscription_color_presets": LIGHT_SUBSCRIPTION_COLOR_PRESETS,
        "participant_seed": _build_participant_seed(
            subscription=subscription, post_data=post_data
        ),
        "reminder_seed": _build_reminder_seed(
            subscription=subscription, post_data=post_data
        ),
        "category_suggestions": CATEGORY_SUGGESTIONS,
        "team_context": team_context,
        "owner_context_label": team_context.name if team_context else "Personal",
        "can_create_direct_subscription": (
            not team_context or is_team_owner(request.user, team_context)
        ),
    }
    return context


def _render_subscription_form(request, form, title, *, subscription=None, team_context=None):
    return render(
        request,
        "subscriptions/form.html",
        _build_subscription_form_context(
            request, form, title, subscription=subscription, team_context=team_context
        ),
    )


def _resolve_team_context(request):
    raw_team_id = request.GET.get("team")
    if request.method == "POST":
        raw_team_id = request.POST.get("team_id", raw_team_id)

    if not raw_team_id:
        return None, None

    try:
        team_id = int(raw_team_id)
    except (TypeError, ValueError):
        return None, "Invalid team context."

    team = Team.objects.filter(pk=team_id).first()
    if not team:
        return None, "Team not found."

    if not is_team_member(request.user, team):
        return None, "You are not a member of that team."

    return team, None


def _subscription_is_accessible(user, subscription):
    if subscription.team_id:
        return is_team_member(user, subscription.team)
    return subscription.user_id == user.pk


def _subscription_is_owner_editable(user, subscription):
    if subscription.team_id:
        return is_team_owner(user, subscription.team)
    return subscription.user_id == user.pk


def _get_accessible_subscription(user, pk, *, require_owner=False):
    subscription = get_object_or_404(Subscription.objects.select_related('team', 'user'), pk=pk)
    if require_owner and not _subscription_is_owner_editable(user, subscription):
        return None
    if not require_owner and not _subscription_is_accessible(user, subscription):
        return None
    return subscription


@login_required
def subscription_list(request):
    return render(request, 'subscriptions/list.html', build_subscription_list_context(request))


def _sanitize_csv_cell(raw_value):
    if raw_value is None:
        return ''

    value = str(raw_value)
    stripped = value.lstrip()
    if stripped and stripped[0] in CSV_FORMULA_PREFIXES:
        return f"'{value}"
    return value


@login_required
def subscription_export_csv(request):
    subscriptions, _ = filter_personal_subscriptions(request)
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
            sorted(participant.name for participant in subscription.participants.all())
        )
        writer.writerow(
            [
                _sanitize_csv_cell(subscription.service_name),
                _sanitize_csv_cell(subscription.plan_name or ''),
                _sanitize_csv_cell(subscription.category),
                subscription.billing_cycle,
                subscription.status,
                'Yes' if subscription.is_shared else 'No',
                _sanitize_csv_cell(participant_names),
                _sanitize_csv_cell(subscription.account_email or ''),
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
                _sanitize_csv_cell(subscription.notes or ''),
            ]
        )

    return response

@login_required
def subscription_create(request):
    team_context, team_error = _resolve_team_context(request)
    if team_error:
        messages.error(request, team_error)
        return redirect('accounts:teams_overview')

    is_team_owner_context = bool(team_context and is_team_owner(request.user, team_context))

    if request.method == 'POST':
        form = SubscriptionForm(request.POST, user=request.user)
        if form.is_valid():
            subscription = form.save(commit=False)
            subscription.user = request.user
            subscription.team = team_context
            reminder_offsets = _parse_reminder_offsets(
                request.POST.getlist("reminder_offsets")
            )
            
            # Handle shared subscription logic
            is_shared = form.cleaned_data.get('is_shared')
            participants_data = []
            if is_shared:
                split_type = form.cleaned_data.get('split_type')
                participants_data, participants_error = _parse_participants_data(request)
                if participants_error:
                    form.add_error(None, participants_error)
                    return _render_subscription_form(
                        request, form, 'Add Subscription', team_context=team_context
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
                            request, form, 'Add Subscription', team_context=team_context
                        )

            else:
                subscription.user_cost = subscription.cost

            participants_to_create = [
                SubscriptionParticipant(
                    subscription=subscription,
                    name=p_data['name'],
                    share_amount=(
                        subscription.user_cost
                        if is_shared and subscription.split_type == 'equal'
                        else p_data['share']
                    ),
                )
                for p_data in participants_data
            ]

            if team_context:
                if not is_team_owner_context:
                    payload = {
                        'service_name': subscription.service_name,
                        'plan_name': subscription.plan_name,
                        'category': subscription.category,
                        'billing_cycle': subscription.billing_cycle,
                        'display_color': subscription.display_color or '',
                        'cost': str(subscription.cost),
                        'user_cost': str(subscription.user_cost),
                        'is_shared': bool(subscription.is_shared),
                        'split_type': subscription.split_type,
                        'currency': subscription.currency,
                        'start_date': subscription.start_date.isoformat() if subscription.start_date else '',
                        'renewal_time': (
                            subscription.renewal_time.isoformat()
                            if subscription.renewal_time
                            else ''
                        ),
                        'status': subscription.status,
                        'reminders_enabled': bool(subscription.reminders_enabled),
                        'notes': subscription.notes or '',
                        'account_email': subscription.account_email or '',
                        # Do not persist account passwords in request payloads.
                        'participants': [
                            {
                                'name': participant.name,
                                'share_amount': (
                                    str(participant.share_amount)
                                    if participant.share_amount is not None
                                    else None
                                ),
                            }
                            for participant in participants_to_create
                        ],
                        'reminder_offsets': reminder_offsets,
                    }

                    team_request = TeamSubscriptionRequest.objects.create(
                        team=team_context,
                        requested_by=request.user,
                        payload=payload,
                    )

                    owner_memberships = (
                        team_context.memberships
                        .select_related('user')
                        .filter(role=TeamMembership.ROLE_OWNER)
                        .exclude(user=request.user)
                    )
                    for owner_membership in owner_memberships:
                        create_notification(
                            recipient=owner_membership.user,
                            actor=request.user,
                            team=team_context,
                            event_type='team.request.submitted',
                            title=f"New subscription request: {subscription.service_name}",
                            body=f"{request.user.email} submitted a request for {subscription.service_name}.",
                            link_url=reverse('accounts:team_detail', args=[team_context.pk]),
                            metadata={'request_id': team_request.pk},
                            send_email_alert=True,
                        )

                    messages.success(
                        request,
                        'Request submitted. Team owners can approve it from Pending Create Requests.',
                    )
                    return redirect('subscriptions:list')

                with transaction.atomic():
                    subscription.save()
                    if participants_to_create:
                        SubscriptionParticipant.objects.bulk_create(participants_to_create)
                    _sync_reminder_offsets(subscription, reminder_offsets)
                    record_due_charge_for_subscription(subscription)

                create_team_notifications(
                    team=team_context,
                    actor=request.user,
                    subscription=subscription,
                    event_type='subscription.created',
                    title=f"New subscription added: {subscription.service_name}",
                    body=f"{request.user.email} added {subscription.service_name}.",
                    link_url=reverse('accounts:team_detail', args=[team_context.pk]),
                    metadata={'subscription_id': subscription.pk},
                    send_email_alert=True,
                )
                return redirect('subscriptions:list')

            with transaction.atomic():
                subscription.save()
                if participants_to_create:
                    SubscriptionParticipant.objects.bulk_create(participants_to_create)
                _sync_reminder_offsets(subscription, reminder_offsets)
                record_due_charge_for_subscription(subscription)
            return redirect('subscriptions:list')
    else:
        initial = _build_subscription_prefill(request.GET)
        form = SubscriptionForm(user=request.user, initial=initial)
    return _render_subscription_form(
        request,
        form,
        'Add Subscription',
        team_context=team_context,
    )

@login_required
def subscription_update(request, pk):
    subscription = _get_accessible_subscription(request.user, pk, require_owner=True)
    if not subscription:
        messages.error(request, 'You do not have permission to edit this subscription.')
        return redirect('accounts:teams_overview')

    team_context = subscription.team
    if request.method == 'POST':
        form = SubscriptionForm(request.POST, instance=subscription, user=request.user)
        if form.is_valid():
            subscription = form.save(commit=False)
            subscription.team = team_context
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
                        team_context=team_context,
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
                            team_context=team_context,
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

            if team_context:
                create_team_notifications(
                    team=team_context,
                    actor=request.user,
                    subscription=subscription,
                    event_type='subscription.updated',
                    title=f"Subscription updated: {subscription.service_name}",
                    body=f"{request.user.email} updated {subscription.service_name}.",
                    link_url=reverse('accounts:team_detail', args=[team_context.pk]),
                    metadata={'subscription_id': subscription.pk},
                    send_email_alert=True,
                )
                return redirect('accounts:team_detail', team_id=team_context.pk)

            return redirect('subscriptions:list')
    else:
        form = SubscriptionForm(instance=subscription, user=request.user)
    return _render_subscription_form(
        request,
        form,
        'Edit Subscription',
        subscription=subscription,
        team_context=team_context,
    )

@login_required
def subscription_delete(request, pk):
    subscription = _get_accessible_subscription(request.user, pk, require_owner=True)
    if not subscription:
        messages.error(request, 'You do not have permission to delete this subscription.')
        return redirect('accounts:teams_overview')

    if request.method == 'POST':
        team_context = subscription.team
        service_name = subscription.service_name
        subscription.delete()
        if team_context:
            create_team_notifications(
                team=team_context,
                actor=request.user,
                event_type='subscription.deleted',
                title=f"Subscription removed: {service_name}",
                body=f"{request.user.email} removed {service_name}.",
                link_url=reverse('accounts:team_detail', args=[team_context.pk]),
                metadata={'service_name': service_name},
                send_email_alert=True,
            )
            return redirect('accounts:team_detail', team_id=team_context.pk)
        return redirect('subscriptions:list')
    return render(request, 'subscriptions/confirm_delete.html', {'subscription': subscription})


@login_required
def delete_reminder_offset(request, pk):
    offset = get_object_or_404(
        ReminderOffset.objects.select_related('subscription', 'subscription__team', 'subscription__user'),
        pk=pk,
    )
    if not _subscription_is_owner_editable(request.user, offset.subscription):
        messages.error(request, 'You do not have permission to edit this subscription.')
        return redirect('accounts:teams_overview')

    subscription_id = offset.subscription.id
    if request.method == 'POST':
        offset.delete()
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'success'})
        return redirect('subscriptions:update', pk=subscription_id)
    return redirect('subscriptions:update', pk=subscription_id)

@login_required
def add_reminder_offset(request, pk):
    subscription = _get_accessible_subscription(request.user, pk, require_owner=True)
    if not subscription:
        messages.error(request, 'You do not have permission to edit this subscription.')
        return redirect('accounts:teams_overview')

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
    subscription = _get_accessible_subscription(request.user, pk, require_owner=True)
    if not subscription:
        return JsonResponse({'status': 'error', 'message': 'Not found'}, status=404)

    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status in ['active', 'paused', 'cancelled']:
            subscription.status = new_status
            subscription.save()
            if subscription.team_id:
                create_team_notifications(
                    team=subscription.team,
                    actor=request.user,
                    subscription=subscription,
                    event_type='subscription.updated',
                    title=f"Subscription updated: {subscription.service_name}",
                    body=f"{request.user.email} changed status to {new_status}.",
                    link_url=reverse('accounts:team_detail', args=[subscription.team_id]),
                    metadata={'subscription_id': subscription.pk, 'status': new_status},
                    send_email_alert=True,
                )
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'success', 'new_status': new_status})
            return redirect('subscriptions:list')
        return JsonResponse({'status': 'error', 'message': 'Invalid status'}, status=400)
    return JsonResponse({'status': 'error', 'message': 'POST required'}, status=405)
