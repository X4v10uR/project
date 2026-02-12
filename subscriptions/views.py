from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from .models import Subscription, ReminderOffset, Card, SubscriptionParticipant
from .forms import SubscriptionForm, CardForm
from django.http import JsonResponse
from django.urls import reverse_lazy

@login_required
def card_list(request):
    cards = Card.objects.filter(user=request.user)
    return render(request, 'subscriptions/cards.html', {'cards': cards})

@login_required
def card_create(request):
    if request.method == 'POST':
        form = CardForm(request.POST)
        if form.is_valid():
            card = form.save(commit=False)
            card.user = request.user
            card.save()
            return redirect('subscriptions:card_list')
    else:
        form = CardForm()
    return render(request, 'subscriptions/card_form.html', {'form': form, 'title': 'Add Card'})

@login_required
def card_update(request, pk):
    card = get_object_or_404(Card, pk=pk, user=request.user)
    if request.method == 'POST':
        form = CardForm(request.POST, instance=card)
        if form.is_valid():
            form.save()
            return redirect('subscriptions:card_list')
    else:
        form = CardForm(instance=card)
    return render(request, 'subscriptions/card_form.html', {'form': form, 'title': 'Edit Card'})

@login_required
def card_delete(request, pk):
    card = get_object_or_404(Card, pk=pk, user=request.user)
    if request.method == 'POST':
        card.delete()
        return redirect('subscriptions:card_list')
    # If using a confirm page, create one. Assuming direct delete for now or reuse existing confirm.
    # But adhering to better UX, let's just do a POST delete from list or a confirm page. 
    # For now, let's reuse confirm_delete.html passing the object.
    return render(request, 'subscriptions/confirm_delete.html', {'object': card, 'type': 'Card'})

@login_required
def subscription_list(request):
    query = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')
    # ... existing code ...
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
        form = SubscriptionForm(request.POST, user=request.user)
        if form.is_valid():
            subscription = form.save(commit=False)
            subscription.user = request.user
            
            # Handle shared subscription logic
            is_shared = form.cleaned_data.get('is_shared')
            if is_shared:
                split_type = form.cleaned_data.get('split_type')
                
                # Get participant names and custom shares from POST data
                participant_names = request.POST.getlist('participant_name')
                participant_shares = request.POST.getlist('participant_share')
                
                # Filter out empty names
                participants_data = []
                for i, name in enumerate(participant_names):
                    if name.strip():
                        share = participant_shares[i] if i < len(participant_shares) and participant_shares[i] else 0
                        participants_data.append({'name': name, 'share': share})
                
                # Validate that we have at least one participant
                if not participants_data:
                    form.add_error(None, 'Please add at least one participant for shared subscriptions.')
                    return render(request, 'subscriptions/form.html', {'form': form, 'title': 'Add Subscription'})
                
                subscription.save() # Save first to get ID
                
                total_participants = len(participants_data) + 1 # +1 for user
                
                if split_type == 'equal':
                    share_per_person = subscription.cost / total_participants
                    subscription.user_cost = share_per_person
                    
                    # Create participants
                    for p_data in participants_data:
                        SubscriptionParticipant.objects.create(
                            subscription=subscription,
                            name=p_data['name'],
                            share_amount=share_per_person
                        )
                else: # Custom split
                    # Calculate user share: Total cost - Sum of other participants' shares
                    total_others_share = sum(float(p['share']) for p in participants_data)
                    subscription.user_cost = float(subscription.cost) - total_others_share
                    
                    # Validate that user_cost is not negative
                    if subscription.user_cost < 0:
                        subscription.delete()
                        form.add_error(None, 'The sum of participant shares exceeds the total cost.')
                        return render(request, 'subscriptions/form.html', {'form': form, 'title': 'Add Subscription'})
                    
                    # Create participants
                    for p_data in participants_data:
                        SubscriptionParticipant.objects.create(
                            subscription=subscription,
                            name=p_data['name'],
                            share_amount=p_data['share']
                        )
                
                subscription.save() # Update user_cost
                
            else:
                subscription.user_cost = subscription.cost
                subscription.save()
            
            # Handle reminder offsets from POST data
            reminder_offsets = request.POST.getlist('reminder_offsets')
            for offset_days in reminder_offsets:
                try:
                    days = int(offset_days)
                    if 1 <= days <= 30:
                        ReminderOffset.objects.create(
                            subscription=subscription,
                            days_before=days
                        )
                except (ValueError, TypeError):
                    pass  # Skip invalid values
            
            return redirect('subscriptions:list')
    else:
        form = SubscriptionForm(user=request.user)
    return render(request, 'subscriptions/form.html', {'form': form, 'title': 'Add Subscription'})

@login_required
def subscription_update(request, pk):
    subscription = get_object_or_404(Subscription, pk=pk, user=request.user)
    if request.method == 'POST':
        form = SubscriptionForm(request.POST, instance=subscription, user=request.user)
        if form.is_valid():
            subscription = form.save(commit=False)
            
            # Handle shared subscription logic
            is_shared = form.cleaned_data.get('is_shared')
            
            if is_shared:
                split_type = form.cleaned_data.get('split_type')
                
                # Clear existing participants
                subscription.participants.all().delete()
                
                # Get participant names and custom shares from POST data
                participant_names = request.POST.getlist('participant_name')
                participant_shares = request.POST.getlist('participant_share')
                
                # Filter out empty names
                participants_data = []
                for i, name in enumerate(participant_names):
                    if name.strip():
                        share = participant_shares[i] if i < len(participant_shares) and participant_shares[i] else 0
                        participants_data.append({'name': name, 'share': share})
                
                # Validate that we have at least one participant
                if not participants_data:
                    form.add_error(None, 'Please add at least one participant for shared subscriptions.')
                    return render(request, 'subscriptions/form.html', {'form': form, 'title': 'Edit Subscription'})
                
                total_participants = len(participants_data) + 1 # +1 for user
                
                if split_type == 'equal':
                    share_per_person = subscription.cost / total_participants
                    subscription.user_cost = share_per_person
                    subscription.save()
                    
                    # Create participants
                    for p_data in participants_data:
                        SubscriptionParticipant.objects.create(
                            subscription=subscription,
                            name=p_data['name'],
                            share_amount=share_per_person
                        )
                else: # Custom split
                    # Calculate user share: Total cost - Sum of other participants' shares
                    total_others_share = sum(float(p['share']) for p in participants_data)
                    subscription.user_cost = float(subscription.cost) - total_others_share
                    
                    # Validate that user_cost is not negative
                    if subscription.user_cost < 0:
                        form.add_error(None, 'The sum of participant shares exceeds the total cost.')
                        return render(request, 'subscriptions/form.html', {'form': form, 'title': 'Edit Subscription'})
                    
                    subscription.save()
                    
                    # Create participants
                    for p_data in participants_data:
                        SubscriptionParticipant.objects.create(
                            subscription=subscription,
                            name=p_data['name'],
                            share_amount=p_data['share']
                        )
            else:
                subscription.user_cost = subscription.cost
                subscription.participants.all().delete() # Cleanup if switched from Shared to Solo
                subscription.save()

            return redirect('subscriptions:list')
    else:
        form = SubscriptionForm(instance=subscription, user=request.user)
    return render(request, 'subscriptions/form.html', {'form': form, 'title': 'Edit Subscription'})

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
        if days_before:
            ReminderOffset.objects.get_or_create(subscription=subscription, days_before=days_before)
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

