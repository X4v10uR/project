from functools import partial

from django.db import transaction

from accounts.models import TeamMembership
from subscriptions.notifications import create_notification
from .models import BalanceAdjustment
from .services import monthly_spend_for_scope


@transaction.atomic
def check_budget(pk):
    budget = BalanceAdjustment.objects.select_for_update().filter(pk=pk).first()
    if budget is None or budget.monthly_limit is None:
        return
    spend = monthly_spend_for_scope(budget.user, budget.scope, budget.currency)
    exceeded = spend > budget.monthly_limit
    if exceeded == budget.over_budget:
        return
    budget.over_budget = exceeded
    budget.save(update_fields=['over_budget'])
    if exceeded:
        create_notification(
            recipient=budget.user, event_type='budget.exceeded',
            title=f'{budget.get_scope_display()} monthly budget exceeded',
            body=f'Recurring spend is {budget.currency} {spend:.2f}. Your limit is {budget.currency} {budget.monthly_limit:.2f}.',
            link_url=f'/dashboard/?scope={budget.scope}&currency={budget.currency}',
        )


def check_budgets(scope=None, user_ids=None):
    budgets = BalanceAdjustment.objects.exclude(monthly_limit=None)
    if scope is not None:
        budgets = budgets.filter(scope=scope, user_id__in=user_ids)
    for pk in budgets.order_by('pk').values_list('pk', flat=True):
        check_budget(pk)


def subscription_changed(sender, instance, raw=False, **kwargs):
    if raw:
        return
    if instance.team_id:
        users = TeamMembership.objects.filter(team_id=instance.team_id).values_list('user_id', flat=True)
        callback = partial(check_budgets, 'teams', users)
    else:
        callback = partial(check_budgets, 'personal', [instance.user_id])
    transaction.on_commit(callback, robust=True)


def membership_changed(sender, instance, raw=False, **kwargs):
    if not raw:
        transaction.on_commit(partial(check_budgets, 'teams', [instance.user_id]), robust=True)
