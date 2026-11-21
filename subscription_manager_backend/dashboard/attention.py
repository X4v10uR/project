from datetime import timedelta

from django.utils import timezone

from accounts.models import TeamMembership
from accounts.renewals import review_details
from finance.delivery import local_now
from subscriptions.models import TeamSubscriptionRequest, Transaction
from subscriptions.planning import visible_subscriptions

from .services import charges_for_scope


def needs_attention(user, scope):
    now = local_now(user)
    today = now.date()
    last = today + timedelta(days=6)
    items = []
    memberships = {m.team_id: m for m in user.team_memberships.all()} if scope == 'teams' else {}
    subs = (visible_subscriptions(user, scope).exclude(status='cancelled')
            .exclude(cancellation_state='confirmed').prefetch_related('price_changes'))
    if scope == 'teams':
        subs = subs.filter(team_id__in=memberships).select_related('team', 'renewal_review__decided_by')

    for sub in subs:
        url = (f'/accounts/teams/{sub.team_id}/#subscription-{sub.pk}' if sub.team_id
               else f'/subscriptions/{sub.pk}/edit/')
        events = []
        if sub.cancel_by_date and today <= sub.cancel_by_date <= last:
            events.append(('deadline', sub.cancel_by_date, 'Review subscription', sub.price_on(sub.cancel_by_date)))
        if sub.trial_end_date and today <= sub.trial_end_date <= last and sub.bills_on(sub.trial_end_date):
            events.append(('trial', sub.trial_end_date, 'Review trial', sub.price_on(sub.trial_end_date)))
        change_dates = {change.effective_on for change in sub.price_changes.all()}
        if sub.introductory_until:
            change_dates.add(sub.introductory_until)
        for day in change_dates:
            if today <= day <= last and sub.price_on(day) > sub.price_on(day - timedelta(days=1)):
                events.append(('price', day, 'Review price', sub.price_on(day)))
        if sub.team_id:
            review = review_details(sub, memberships[sub.team_id], today)
            deadline = review['due_on']
            if review['can_decide'] and not review['decision'] and deadline and deadline <= last:
                events.append(('decision', deadline, 'Review renewal', sub.price_on(review['renewal_date'])))
        for kind, day, action, amount in events:
            items.append({'id': f'{kind}-{sub.pk}-{day}', 'kind': kind, 'service': sub.service_name,
                          'workspace': sub.team.name if sub.team_id else None,
                          'date': day, 'amount': format(amount, '.2f'), 'currency': sub.currency,
                          'action': action, 'url': url})

    failed = charges_for_scope(user, scope).filter(payment_status=Transaction.PaymentStatus.FAILED).select_related('team')
    for charge in failed:
        items.append({'id': f'payment-{charge.pk}', 'kind': 'payment', 'service': charge.service_name_snapshot,
                      'workspace': charge.team.name if charge.team_id else None,
                      'date': charge.charged_for_date, 'amount': str(charge.amount), 'currency': charge.currency,
                      'action': 'Review charge', 'url': f'/dashboard/history/?scope={scope}&charge={charge.pk}'})
    if scope == 'teams':
        pending = TeamSubscriptionRequest.objects.filter(
            status=TeamSubscriptionRequest.STATUS_PENDING, team__memberships__user=user,
            team__memberships__role=TeamMembership.ROLE_OWNER).select_related('team')
        for request in pending:
            items.append({'id': f'approval-{request.pk}', 'kind': 'approval',
                          'service': request.payload.get('service_name') or request.team.name, 'workspace': request.team.name,
                          'date': timezone.localtime(request.created_at, now.tzinfo).date(),
                          'amount': request.payload.get('cost'), 'currency': request.payload.get('currency'),
                          'action': 'Review request', 'url': f'/accounts/teams/{request.team_id}/#request-{request.pk}'})

    priority = {'payment': 0, 'deadline': 1, 'decision': 2, 'trial': 3, 'price': 4, 'approval': 5}
    return sorted(items, key=lambda item: (item['date'], priority[item['kind']], item['service'].casefold(), item['id']))
