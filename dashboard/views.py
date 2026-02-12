from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.utils import timezone
from datetime import timedelta
from subscriptions.models import Subscription

# from decimal import Decimal
# from django.db.models import Count, Q

def landing_page(request):
    if request.user.is_authenticated:
        return redirect('dashboard:home')
    return render(request, 'landing.html')

@login_required
def home(request):
    user_subs = Subscription.objects.filter(user=request.user)
    active_subs = user_subs.filter(status='active')
    
    # Calculate Monthly Spend
    monthly_spend = 0
    for sub in active_subs:
        cost = sub.user_cost if sub.is_shared else sub.cost
        
        if sub.billing_cycle == 'monthly':
            monthly_spend += cost
        elif sub.billing_cycle == 'yearly':
            monthly_spend += cost / 12
        elif sub.billing_cycle == 'weekly':
            monthly_spend += cost * 4  # Approximation

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
    shared_count = user_subs.filter(is_shared=True, status='active').count()

    paused_subs = user_subs.filter(status='paused')
    cancelled_subs = user_subs.filter(status='cancelled')
    shared_subs = user_subs.filter(is_shared=True, status='active')

    # Calculate Average Monthly Spend per Active Service
    avg_monthly_spend = 0
    if active_count > 0:
        avg_monthly_spend = monthly_spend / active_count

    context = {
        'total_active': active_count,
        'total_paused': paused_count,
        'total_cancelled': cancelled_count,
        'total_shared': shared_count,
        'active_subscriptions': active_subs,
        'paused_subscriptions': paused_subs,
        'cancelled_subscriptions': cancelled_subs,
        'shared_subscriptions': shared_subs,
        'monthly_spend': round(monthly_spend, 2),
        'yearly_spend': round(yearly_spend, 2),
        'avg_monthly_spend': round(avg_monthly_spend, 2),
        'upcoming_renewals': upcoming_renewals,
        'status_dist': {
            'active': active_count,
            'cancelled': cancelled_count,
            'paused': paused_count,
            'shared': shared_count,
        }
    }
    return render(request, 'dashboard/home.html', context)




# @login_required
# def home(request):
#     user_subs = Subscription.objects.filter(user=request.user)

#     # Group status counts in ONE query
#     status_counts = user_subs.aggregate(
#         active=Count('id', filter=Q(status='active')),
#         cancelled=Count('id', filter=Q(status='cancelled')),
#         paused=Count('id', filter=Q(status='paused')),
#         shared=Count('id', filter=Q(status='active', is_shared=True)),
#     )

#     active_subs = user_subs.filter(status='active')
#     paused_subs = user_subs.filter(status='paused')
#     cancelled_subs = user_subs.filter(status='cancelled')
#     shared_subs = user_subs.filter(status='active', is_shared=True)

#     # Monthly Spend Calculation
#     monthly_spend = Decimal('0.00')

#     for sub in active_subs:
#         cost = sub.user_cost if sub.is_shared else sub.cost
#         cost = Decimal(cost)

#         if sub.billing_cycle == 'monthly':
#             monthly_spend += cost
#         elif sub.billing_cycle == 'yearly':
#             monthly_spend += cost / Decimal('12')
#         elif sub.billing_cycle == 'weekly':
#             monthly_spend += cost * Decimal('52') / Decimal('12')

#     yearly_spend = monthly_spend * Decimal('12')

#     # Upcoming Renewals
#     today = timezone.now().date()
#     next_30_days = today + timedelta(days=30)

#     upcoming_renewals = active_subs.filter(
#         renewal_date__range=[today, next_30_days]
#     ).order_by('renewal_date')

#     # Average Spend
#     avg_monthly_spend = (
#         monthly_spend / status_counts['active']
#         if status_counts['active'] > 0 else Decimal('0.00')
#     )

#     context = {
#         'total_active': status_counts['active'],
#         'total_paused': status_counts['paused'],
#         'total_cancelled': status_counts['cancelled'],
#         'total_shared': status_counts['shared'],
#         'active_subscriptions': active_subs,
#         'paused_subscriptions': paused_subs,
#         'cancelled_subscriptions': cancelled_subs,
#         'shared_subscriptions': shared_subs,
#         'monthly_spend': round(monthly_spend, 2),
#         'yearly_spend': round(yearly_spend, 2),
#         'avg_monthly_spend': round(avg_monthly_spend, 2),
#         'upcoming_renewals': upcoming_renewals,
#         'status_dist': status_counts,
#     }

#     return render(request, 'dashboard/home.html', context)
