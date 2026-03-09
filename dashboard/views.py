import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from django.utils import timezone

from subscriptions.models import InAppNotification
from subscriptions.notifications import (
    notification_unread_count,
    push_bulk_read,
    push_updated,
    serialize_notification,
)

from .services import build_dashboard_view_model, set_user_balance_target


def landing_page(request):
    if request.user.is_authenticated:
        return redirect('dashboard:home')
    return render(request, 'landing.html')


@login_required
def home(request):
    scope = (request.GET.get('scope') or 'personal').lower()
    context = build_dashboard_view_model(request.user, scope=scope)
    return render(request, 'dashboard/dashboard.html', context)


@login_required
@require_POST
def adjust_balance(request):
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return JsonResponse(
            {'ok': False, 'message': 'Invalid JSON payload.'},
            status=400,
        )

    raw_target = payload.get('target_balance')
    if raw_target is None:
        return JsonResponse(
            {'ok': False, 'message': 'target_balance is required.'},
            status=400,
        )

    try:
        target_balance = Decimal(str(raw_target))
    except (InvalidOperation, TypeError):
        return JsonResponse(
            {'ok': False, 'message': 'target_balance must be a valid number.'},
            status=400,
        )

    if target_balance < Decimal('-1000000') or target_balance > Decimal('1000000'):
        return JsonResponse(
            {'ok': False, 'message': 'Balance must be between -1000000 and 1000000.'},
            status=400,
        )

    scope = payload.get('scope') or request.GET.get('scope') or 'personal'
    snapshot = set_user_balance_target(request.user, target_balance, scope=scope)
    return JsonResponse({'ok': True, **snapshot})


@login_required
def notifications_page(request):
    notifications = InAppNotification.objects.filter(recipient=request.user)[:50]
    return render(
        request,
        'dashboard/notifications.html',
        {
            'notifications': notifications,
        },
    )


@login_required
def notifications_list_api(request):
    notifications = list(
        InAppNotification.objects.filter(recipient=request.user)[:20]
    )
    return JsonResponse(
        {
            'ok': True,
            'notifications': [serialize_notification(notification) for notification in notifications],
            'unread_count': notification_unread_count(request.user),
        }
    )


@login_required
def notifications_unread_count_api(request):
    return JsonResponse({'ok': True, 'unread_count': notification_unread_count(request.user)})


@login_required
@require_POST
def notification_mark_read_api(request, pk):
    notification = InAppNotification.objects.filter(recipient=request.user, pk=pk).first()
    if not notification:
        return JsonResponse({'ok': False, 'message': 'Not found.'}, status=404)

    notification.mark_read()
    push_updated(notification)
    return JsonResponse({'ok': True, 'unread_count': notification_unread_count(request.user)})


@login_required
@require_POST
def notifications_mark_all_read_api(request):
    notifications = InAppNotification.objects.filter(recipient=request.user, is_read=False)
    notifications.update(is_read=True, read_at=timezone.now())
    push_bulk_read(request.user)
    return JsonResponse({'ok': True, 'unread_count': notification_unread_count(request.user)})
