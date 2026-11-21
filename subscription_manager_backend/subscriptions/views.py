import csv
import json
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.validators import DecimalValidator
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.models import Team
from accounts.services import is_team_member, is_team_owner

from .color_utils import (
    LIGHT_SUBSCRIPTION_COLOR_PRESETS,
    normalize_subscription_display_color,
)
from .forms import SubscriptionForm
from .list_context import build_subscription_list_context, filter_personal_subscriptions
from .models import ReminderOffset, Subscription
from .money import equal_share
from .workflows import change_subscription_status, remove_subscription, save_subscription


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
        if len(name) > 100:
            return None, 'Participant names must be 100 characters or fewer.'

        raw_share = '0'
        if i < len(participant_shares):
            raw_share = (participant_shares[i] or '0').strip()

        try:
            share = Decimal(raw_share or '0')
        except (InvalidOperation, TypeError):
            return None, 'Participant shares must be valid numbers.'

        if not share.is_finite() or share < 0:
            return None, 'Participant shares cannot be negative.'
        try:
            DecimalValidator(max_digits=10, decimal_places=2)(share)
        except ValidationError as exc:
            return None, exc.messages[0]

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
    if value.startswith("'") or stripped.startswith(CSV_FORMULA_PREFIXES):
        return f"'{value}"
    return value


@login_required
def subscription_export_csv(request):
    return build_subscription_csv(request)


def build_subscription_csv(request):
    subscriptions, _ = filter_personal_subscriptions(request)
    subscriptions = subscriptions.prefetch_related('participants', 'offsets', 'price_changes')
    today = timezone.localdate()

    response = HttpResponse(content_type='text/csv')
    response['Cache-Control'] = 'no-store'
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
            'Split Type', 'Participant Shares', 'Reminders Enabled', 'Reminder Offsets', 'Display Color', 'Trial End Date', 'Cancel By Date',
            'Cancellation Url', 'Cancellation State', 'Cancellation Notes', 'Access Until', 'Pause From', 'Resume On', 'Introductory Cost', 'Introductory Until',
            'Paid Through',
        ]
    )

    for subscription in subscriptions:
        price = subscription.regular_price_on(today)
        people = sorted(subscription.participants.all(), key=lambda person: person.pk)
        participant_names = ', '.join(sorted(person.name for person in people))
        participant_shares = []
        for index, person in enumerate(people, 1):
            share = equal_share(price, len(people) + 1, index) if subscription.split_type == 'equal' else person.share_amount or 0
            participant_shares.append({'name': person.name, 'share': str(share)})
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
                _sanitize_csv_cell(subscription.currency),
                str(price),
                str(subscription.share_of(price)),
                subscription.start_date.isoformat() if subscription.start_date else '',
                subscription.renewal_date.isoformat()
                if subscription.renewal_date
                else '',
                subscription.renewal_time.strftime('%H:%M')
                if subscription.renewal_time
                else '',
                _sanitize_csv_cell(subscription.notes or ''),
                subscription.split_type,
                json.dumps(participant_shares),
                'Yes' if subscription.reminders_enabled else 'No',
                ','.join(str(offset.days_before) for offset in subscription.offsets.all()),
                subscription.display_color, subscription.trial_end_date or '', subscription.cancel_by_date or '',
                _sanitize_csv_cell(subscription.cancellation_url), subscription.cancellation_state,
                _sanitize_csv_cell(subscription.cancellation_notes), subscription.access_until or '', subscription.pause_from or '', subscription.resume_on or '',
                str(subscription.introductory_cost) if subscription.introductory_cost is not None else '', subscription.introductory_until or '',
                subscription.paid_through or '',
            ]
        )

    return response

def _save_subscription_form(request, form, team_context):
    subscription = form.save(commit=False)
    if form.data.get('account_password'):
        subscription.set_account_password(form.cleaned_data['account_password'])
    if not subscription.pk:
        subscription.user = request.user
    subscription.team = team_context
    participants = []
    if subscription.is_shared:
        participants, participants_error = _parse_participants_data(request)
        if participants_error:
            form.add_error(None, participants_error)
            return False
    try:
        team_request = save_subscription(
            subscription,
            actor=request.user,
            participants=participants,
            reminder_offsets=_parse_reminder_offsets(request.POST.getlist("reminder_offsets")),
        )
    except ValidationError as exc:
        form.add_error(None, exc)
        return False
    if team_request:
        messages.success(
            request,
            'Request submitted. Team owners can approve it from Pending Create Requests.',
        )
    return True


@login_required
def subscription_create(request):
    team_context, team_error = _resolve_team_context(request)
    if team_error:
        messages.error(request, team_error)
        return redirect('accounts:teams_overview')

    if request.method == 'POST':
        form = SubscriptionForm(request.POST, user=request.user)
        if form.is_valid() and _save_subscription_form(request, form, team_context):
            return redirect('subscriptions:list')
    else:
        form = SubscriptionForm(user=request.user, initial=_build_subscription_prefill(request.GET))
    return _render_subscription_form(request, form, 'Add Subscription', team_context=team_context)


@login_required
def subscription_update(request, pk):
    subscription = _get_accessible_subscription(request.user, pk, require_owner=True)
    if not subscription:
        messages.error(request, 'You do not have permission to edit this subscription.')
        return redirect('accounts:teams_overview')

    form = SubscriptionForm(
        request.POST if request.method == 'POST' else None,
        instance=subscription,
        user=request.user,
        initial={'cost': subscription.regular_price_on(timezone.localdate())},
    )
    if request.method == 'POST' and form.is_valid() and _save_subscription_form(request, form, subscription.team):
        if subscription.team_id:
            return redirect('accounts:team_detail', team_id=subscription.team_id)
        return redirect('subscriptions:list')
    return _render_subscription_form(
        request, form, 'Edit Subscription', subscription=subscription, team_context=subscription.team
    )


@login_required
def subscription_delete(request, pk):
    subscription = _get_accessible_subscription(request.user, pk, require_owner=True)
    if not subscription:
        messages.error(request, 'You do not have permission to delete this subscription.')
        return redirect('accounts:teams_overview')

    if request.method == 'POST':
        team_id = subscription.team_id
        remove_subscription(subscription, actor=request.user)
        if team_id:
            return redirect('accounts:team_detail', team_id=team_id)
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
            change_subscription_status(subscription, actor=request.user, status=new_status)
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'success', 'new_status': new_status})
            return redirect('subscriptions:list')
        return JsonResponse({'status': 'error', 'message': 'Invalid status'}, status=400)
    return JsonResponse({'status': 'error', 'message': 'POST required'}, status=405)
