from decimal import Decimal
from functools import partial
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from subscriptions.models import Subscription
from subscriptions.money import monthly_equivalent
from subscriptions.notifications import create_notification
from .models import SpendingBudget
from .permissions import require_team


class BudgetInput(serializers.ModelSerializer):
    team_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)

    class Meta:
        model = SpendingBudget
        fields = ('team_id', 'category', 'currency', 'monthly_limit', 'warning_percent')
        extra_kwargs = {'monthly_limit': {'min_value': Decimal('.01')}, 'warning_percent': {'min_value': 1, 'max_value': 99}}

    def validate_currency(self, value):
        if len(value) != 3 or not value.isascii() or not value.isalpha():
            raise serializers.ValidationError('Use a three-letter currency code.')
        return value.upper()

    def validate(self, values):
        require_team(self.context['user'], values.get('team_id'), 'pay')
        return values

    def create(self, validated_data):
        budget, _ = SpendingBudget.objects.update_or_create(
            user=self.context['user'], team_id=validated_data.get('team_id'),
            category=validated_data.get('category', ''), currency=validated_data['currency'],
            defaults=validated_data,
        )
        return budget


def spend(budget):
    subs = Subscription.objects.filter(currency=budget.currency)
    subs = subs.filter(team_id=budget.team_id) if budget.team_id else subs.filter(user=budget.user, team__isnull=True)
    if budget.category:
        subs = subs.filter(category__iexact=budget.category)
    today = timezone.localdate()
    return sum((monthly_equivalent(s.price_on(today) if budget.team_id else s.share_on(today), s.billing_cycle)
        for s in subs.prefetch_related('price_changes', 'participants') if s.bills_on(today)), Decimal('0')).quantize(Decimal('.01'))


@transaction.atomic
def check_budget(pk):
    budget = SpendingBudget.objects.select_for_update().filter(pk=pk).first()
    if not budget:
        return
    from .permissions import team_permission
    if budget.team_id and not team_permission(budget.user, budget.team_id, 'pay'):
        return
    value = spend(budget)
    percent = value / budget.monthly_limit * 100
    level = 2 if percent >= 100 else 1 if percent >= budget.warning_percent else 0
    if level > budget.last_level:
        label = budget.category or (budget.team.name if budget.team_id else 'Personal')
        create_notification(recipient=budget.user, team=budget.team, event_type='budget.warning',
            title=f'{label}: budget {"exceeded" if level == 2 else "warning"}',
            body=f'Monthly commitment is {budget.currency} {value} of {budget.monthly_limit} ({percent:.0f}%).',
            link_url='/planning/budgets/', send_email_alert=True)
    if level != budget.last_level:
        budget.last_level = level
        budget.save(update_fields=['last_level'])


def check_all():
    for pk in SpendingBudget.objects.values_list('pk', flat=True):
        check_budget(pk)


def subscription_changed(sender, instance, raw=False, **kwargs):
    if raw:
        return
    budgets = SpendingBudget.objects.filter(team_id=instance.team_id) if instance.team_id else SpendingBudget.objects.filter(user=instance.user, team__isnull=True)
    for pk in budgets.values_list('pk', flat=True):
        transaction.on_commit(partial(check_budget, pk), robust=True)
