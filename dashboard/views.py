import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .services import build_dashboard_view_model, set_user_balance_target


def landing_page(request):
    if request.user.is_authenticated:
        return redirect('dashboard:home')
    return render(request, 'landing.html')


@login_required
def home(request):
    context = build_dashboard_view_model(request.user)
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

    snapshot = set_user_balance_target(request.user, target_balance)
    return JsonResponse({'ok': True, **snapshot})
