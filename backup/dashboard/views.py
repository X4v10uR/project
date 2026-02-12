from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.utils import timezone
from datetime import timedelta
from subscriptions.models import Subscription

@login_required
def home(request):
    user_subs = Subscription.objects.filter(user=request.user)
    active_subs = user_subs.filter(status='active')
    
    # Calculate Monthly Spend
    monthly_spend = 0
    for sub in active_subs:
        if sub.billing_cycle == 'monthly':
            monthly_spend += sub.cost
        elif sub.billing_cycle == 'yearly':
            monthly_spend += sub.cost / 12
        elif sub.billing_cycle == 'weekly':
            monthly_spend += sub.cost * 4  # Approximation

    # Calculate Yearly Spend
    yearly_spend = monthly_spend * 12

    # Upcoming Renewals (Next 30 days)
    today = timezone.now().date()
    next_30_days = today + timedelta(days=30)
    upcoming_renewals = active_subs.filter(renewal_date__range=[today, next_30_days]).order_by('renewal_date')

    # Status Distribution
    active_count = user_subs.filter(status='active').count()
    cancelled_count = user_subs.filter(status='cancelled').count()
    paused_count = user_subs.filter(status='paused').count()

    context = {
        'total_active': active_count,
        'monthly_spend': round(monthly_spend, 2),
        'yearly_spend': round(yearly_spend, 2),
        'upcoming_renewals': upcoming_renewals,
        'status_dist': {
            'active': active_count,
            'cancelled': cancelled_count,
            'paused': paused_count,
        }
    }
    return render(request, 'dashboard/home.html', context)
