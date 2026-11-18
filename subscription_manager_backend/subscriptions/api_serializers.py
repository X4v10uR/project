from decimal import Decimal

from rest_framework import serializers
from django.utils import timezone

from .forms import SubscriptionForm
from .models import Subscription, SubscriptionParticipant


class ParticipantInput(serializers.Serializer):
    member_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    name = serializers.CharField(max_length=100)
    share = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal('0'),
        default=Decimal('0'),
    )


class SubscriptionInput(serializers.Serializer):
    team_id = serializers.IntegerField(min_value=1, required=False)
    participants = ParticipantInput(many=True, required=False, default=list)
    reminder_offsets = serializers.ListField(
        child=serializers.IntegerField(min_value=1, max_value=30), required=False, default=list
    )


class SubscriptionStatusInput(serializers.Serializer):
    status = serializers.ChoiceField(choices=Subscription.STATUS_CHOICES)


class ParticipantSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionParticipant
        fields = ('name', 'share_amount', 'member_id')


class SubscriptionSerializer(serializers.ModelSerializer):
    cost = serializers.SerializerMethodField()
    current_cost = serializers.SerializerMethodField()
    current_user_cost = serializers.SerializerMethodField()
    has_password = serializers.SerializerMethodField()
    participants = ParticipantSerializer(many=True)
    reminder_offsets = serializers.SlugRelatedField(source='offsets', slug_field='days_before', many=True, read_only=True)
    card_nickname = serializers.CharField(source='card.nickname', default=None)
    icon_url = serializers.CharField(source='get_icon_url')
    fallback_icon = serializers.CharField(source='get_fallback_icon')

    class Meta:
        model = Subscription
        fields = (
            'id', 'team', 'service_name', 'display_color', 'plan_name', 'category', 'billing_cycle',
            'cost', 'user_cost', 'currency', 'start_date', 'trial_end_date', 'cancel_by_date', 'renewal_date', 'renewal_time',
            'status', 'reminders_enabled', 'reminder_offsets', 'card', 'card_nickname', 'notes',
            'is_shared', 'split_type', 'account_email', 'has_password', 'participants', 'icon_url', 'fallback_icon',
            'cancellation_url', 'cancellation_state', 'cancellation_notes', 'access_until',
            'pause_from', 'resume_on', 'introductory_cost', 'introductory_until', 'last_reviewed_on', 'usage_rating',
            'current_cost', 'current_user_cost',
        )

    def get_has_password(self, instance):
        return bool(instance.account_password)

    def get_current_cost(self, instance):
        return format(instance.price_on(timezone.localdate()), '.2f')

    def get_cost(self, instance):
        return format(instance.regular_price_on(timezone.localdate()), '.2f')

    def get_current_user_cost(self, instance):
        return format(instance.share_on(timezone.localdate()), '.2f')


def subscription_form(data, *, user, instance=None):
    form_fields = SubscriptionForm.base_fields
    fields = {key: value for key, value in data.items() if key in form_fields}
    invalid_fields = {
        field: ['Enter a single value.']
        for field, value in fields.items()
        if value is not None and not isinstance(value, (str, int, float, bool))
    }
    if invalid_fields:
        raise serializers.ValidationError(invalid_fields)

    if instance is not None:
        fields.setdefault('category', instance.category or 'Other')
        for field in ('trial_end_date', 'cancel_by_date', 'cancellation_url', 'cancellation_state', 'cancellation_notes', 'access_until', 'pause_from', 'resume_on', 'introductory_cost', 'introductory_until'):
            fields.setdefault(field, getattr(instance, field))
    if instance is None:
        fields.setdefault('reminders_enabled', True)
        preferred_currency = user.preferred_currency
        if len(preferred_currency) != 3 or not preferred_currency.isascii() or not preferred_currency.isalpha():
            preferred_currency = 'USD'
        fields.setdefault('currency', preferred_currency)
        fields.setdefault('status', 'active')
        fields.setdefault('split_type', 'equal')
        fields.setdefault('cancellation_state', 'none')
        fields.setdefault('category', 'Other')
    form = SubscriptionForm(fields, instance=instance, user=user)
    if not form.is_valid():
        raise serializers.ValidationError(dict(form.errors))
    return form
