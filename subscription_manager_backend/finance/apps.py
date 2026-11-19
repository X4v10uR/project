from django.apps import AppConfig


class FinanceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'finance'

    def ready(self):
        from django.contrib.auth.signals import user_logged_out
        from django.db.models.signals import post_save, post_delete
        from subscriptions.models import Subscription
        from .budgets import subscription_changed
        from .models import Receipt, PushSubscription
        from django.db import transaction
        def delete_receipt_file(sender, instance, **kwargs):
            if instance.file:
                storage, name = instance.file.storage, instance.file.name
                transaction.on_commit(lambda: storage.delete(name))
        def delete_session_push(sender, request, user, **kwargs):
            if request is not None and user is not None and user.is_authenticated and user.pk is not None:
                PushSubscription.objects.filter(user=user, session_key=request.session.session_key).delete()
        user_logged_out.connect(delete_session_push, weak=False, dispatch_uid='finance.push.logout')
        post_delete.connect(delete_receipt_file, sender=Receipt, weak=False, dispatch_uid='finance.receipt.delete')
        post_save.connect(subscription_changed, sender=Subscription, dispatch_uid='finance.budgets.save')
        post_delete.connect(subscription_changed, sender=Subscription, dispatch_uid='finance.budgets.delete')
