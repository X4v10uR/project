from django.apps import AppConfig


class FinanceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'finance'

    def ready(self):
        from django.db.models.signals import post_save, post_delete
        from subscriptions.models import Subscription
        from .budgets import subscription_changed
        from .models import Receipt
        from django.db import transaction
        def delete_receipt_file(sender, instance, **kwargs):
            if instance.file:
                storage, name = instance.file.storage, instance.file.name
                transaction.on_commit(lambda: storage.delete(name))
        post_delete.connect(delete_receipt_file, sender=Receipt, weak=False, dispatch_uid='finance.receipt.delete')
        post_save.connect(subscription_changed, sender=Subscription, dispatch_uid='finance.budgets.save')
        post_delete.connect(subscription_changed, sender=Subscription, dispatch_uid='finance.budgets.delete')
