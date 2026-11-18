from django.apps import AppConfig


class DashboardConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'dashboard'

    def ready(self):
        from django.db.models.signals import post_delete, post_save
        from accounts.models import TeamMembership
        from subscriptions.models import Subscription
        from .budgets import membership_changed, subscription_changed

        for signal in (post_save, post_delete):
            signal.connect(subscription_changed, sender=Subscription)
            signal.connect(membership_changed, sender=TeamMembership)
