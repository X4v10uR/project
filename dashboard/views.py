from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .services import build_dashboard_view_model


def landing_page(request):
    if request.user.is_authenticated:
        return redirect('dashboard:home')
    return render(request, 'landing.html')


@login_required
def home(request):
    context = build_dashboard_view_model(request.user)
    return render(request, 'dashboard/dashboard.html', context)
