"""Concurrency tokens for subscription editors without exposing form values."""
import json

from django.utils.crypto import salted_hmac


class StaleSubscriptionEdit(Exception):
    pass


def edit_revision(subscription):
    prices = [(price.pk, str(price.effective_on), str(price.previous_cost), str(price.cost))
              for price in subscription.price_changes.all()]
    # The scheduler can advance renewal_date without editing the plan.
    fields = [
        subscription.pk, str(subscription.updated_at), subscription.service_name,
        str(subscription.cost), subscription.currency, subscription.configured_status, prices,
    ]
    material = json.dumps(fields, separators=(',', ':'))
    return salted_hmac('dues.subscription.edit', material, algorithm='sha256').hexdigest()


def require_edit_revision(subscription, expected):
    if expected is not None and expected != edit_revision(subscription):
        raise StaleSubscriptionEdit('This subscription changed after you opened it. Reload to review the latest details before saving.')
