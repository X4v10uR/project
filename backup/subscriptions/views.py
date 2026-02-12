from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from .models import Subscription
from .forms import SubscriptionForm

@login_required
def subscription_list(request):
    query = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')
    cycle_filter = request.GET.get('cycle', '')
    sort_by = request.GET.get('sort', 'renewal_date')

    subscriptions = Subscription.objects.filter(user=request.user)

    if query:
        subscriptions = subscriptions.filter(service_name__icontains=query)
    if status_filter:
        subscriptions = subscriptions.filter(status=status_filter)
    if cycle_filter:
        subscriptions = subscriptions.filter(billing_cycle=cycle_filter)
    
    if sort_by in ['cost', 'renewal_date', 'service_name']:
        subscriptions = subscriptions.order_by(sort_by)

    return render(request, 'subscriptions/list.html', {
        'subscriptions': subscriptions,
        'query': query,
        'status_filter': status_filter,
        'cycle_filter': cycle_filter,
        'sort_by': sort_by
    })

@login_required
def subscription_create(request):
    if request.method == 'POST':
        form = SubscriptionForm(request.POST)
        if form.is_valid():
            subscription = form.save(commit=False)
            subscription.user = request.user
            subscription.save()
            return redirect('subscriptions:list')
    else:
        form = SubscriptionForm()
    return render(request, 'subscriptions/form.html', {'form': form, 'title': 'Add Subscription'})

@login_required
def subscription_update(request, pk):
    subscription = get_object_or_404(Subscription, pk=pk, user=request.user)
    if request.method == 'POST':
        form = SubscriptionForm(request.POST, instance=subscription)
        if form.is_valid():
            form.save()
            return redirect('subscriptions:list')
    else:
        form = SubscriptionForm(instance=subscription)
    return render(request, 'subscriptions/form.html', {'form': form, 'title': 'Edit Subscription'})

@login_required
def subscription_delete(request, pk):
    subscription = get_object_or_404(Subscription, pk=pk, user=request.user)
    if request.method == 'POST':
        subscription.delete()
        return redirect('subscriptions:list')
    return render(request, 'subscriptions/confirm_delete.html', {'subscription': subscription})
