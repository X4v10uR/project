from decimal import Decimal

from rest_framework import serializers

from .forms import SubscriptionForm
from .models import Subscription, SubscriptionParticipant


class ParticipantInput(serializers.Serializer):
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
        fields = ('name', 'share_amount')


class SubscriptionSerializer(serializers.ModelSerializer):
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
            'cost', 'user_cost', 'currency', 'start_date', 'renewal_date', 'renewal_time',
            'status', 'reminders_enabled', 'reminder_offsets', 'card', 'card_nickname', 'notes',
            'is_shared', 'split_type', 'account_email', 'has_password', 'participants', 'icon_url', 'fallback_icon',
        )

    def get_has_password(self, instance):
        return bool(instance.account_password)


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

    if instance is None:
        fields.setdefault('reminders_enabled', True)
        fields.setdefault('currency', 'USD')
        fields.setdefault('status', 'active')
        fields.setdefault('split_type', 'equal')
    form = SubscriptionForm(fields, instance=instance, user=user)
    if not form.is_valid():
        raise serializers.ValidationError(dict(form.errors))
    return form
