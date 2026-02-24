import os
import django
from datetime import date, time, timedelta
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'subly.settings')
django.setup()

from accounts.models import User
from subscriptions.models import Subscription, Transaction


DEMO_EMAIL = 'demo@subly.com'
DEMO_PASSWORD = 'demo1234'


def _days_ago(base_date, days):
    return base_date - timedelta(days=days)


def seed_data():
    user, created = User.objects.get_or_create(email=DEMO_EMAIL)
    user.set_password(DEMO_PASSWORD)
    user.save()

    if created:
        print(f"Created demo user: {DEMO_EMAIL}")
    else:
        print(f"Updated demo user password: {DEMO_EMAIL}")

    # Reset subscriptions so this script is deterministic every run.
    Subscription.objects.filter(user=user).delete()
    print("Cleared existing demo subscriptions and related transactions.")

    today = date.today()
    demo_subscriptions = [
        {
            'service_name': 'Netflix',
            'category': 'Streaming',
            'billing_cycle': 'monthly',
            'cost': Decimal('15.99'),
            'status': 'active',
            'start_date': _days_ago(today, 220),
        },
        {
            'service_name': 'Spotify',
            'category': 'Music',
            'billing_cycle': 'monthly',
            'cost': Decimal('9.99'),
            'status': 'active',
            'start_date': _days_ago(today, 180),
        },
        {
            'service_name': 'AWS',
            'category': 'Cloud',
            'billing_cycle': 'monthly',
            'cost': Decimal('45.50'),
            'status': 'active',
            'start_date': _days_ago(today, 150),
        },
        {
            'service_name': 'Notion',
            'category': 'Software',
            'billing_cycle': 'monthly',
            'cost': Decimal('12.00'),
            'status': 'active',
            'start_date': _days_ago(today, 90),
        },
        {
            'service_name': 'Disney+',
            'category': 'Streaming',
            'billing_cycle': 'yearly',
            'cost': Decimal('79.99'),
            'status': 'active',
            'start_date': _days_ago(today, 360),
        },
        {
            'service_name': 'GitHub',
            'category': 'Software',
            'billing_cycle': 'monthly',
            'cost': Decimal('4.00'),
            'status': 'paused',
            'start_date': _days_ago(today, 110),
        },
        {
            'service_name': 'Adobe CC',
            'category': 'Software',
            'billing_cycle': 'monthly',
            'cost': Decimal('52.99'),
            'status': 'cancelled',
            'start_date': _days_ago(today, 260),
        },
    ]

    subscriptions_by_service = {}
    for entry in demo_subscriptions:
        subscription = Subscription.objects.create(
            user=user,
            service_name=entry['service_name'],
            category=entry['category'],
            billing_cycle=entry['billing_cycle'],
            cost=entry['cost'],
            currency='USD',
            renewal_time=time(9, 0),
            split_type='equal',
            account_email='demo@subly.com',
            account_password='demo-password',
            start_date=entry['start_date'],
            status=entry['status'],
            notes=f"Seeded demo subscription for {entry['service_name']}.",
        )
        subscriptions_by_service[entry['service_name']] = subscription
        print(
            f"Created subscription: {entry['service_name']} "
            f"({entry['status']}) start={entry['start_date']}"
        )

    # Fixed 30-day trend data for dashboard graph testing.
    # Each tuple: (service_name, days_ago, amount)
    trend_transactions = [
        ('Netflix', 29, Decimal('15.99')),
        ('Spotify', 26, Decimal('9.99')),
        ('AWS', 22, Decimal('45.50')),
        ('Notion', 19, Decimal('12.00')),
        ('Netflix', 15, Decimal('15.99')),
        ('Disney+', 12, Decimal('79.99')),
        ('Spotify', 8, Decimal('9.99')),
        ('AWS', 5, Decimal('45.50')),
        ('Notion', 2, Decimal('12.00')),
    ]

    for service_name, days_ago, amount in trend_transactions:
        subscription = subscriptions_by_service.get(service_name)
        if not subscription:
            continue

        charge_date = _days_ago(today, days_ago)
        Transaction.objects.create(
            user=user,
            subscription=subscription,
            service_name_snapshot=service_name,
            amount=amount,
            currency='USD',
            charged_for_date=charge_date,
            source=Transaction.SOURCE_RENEWAL,
        )
        print(
            f"Created transaction: {service_name} "
            f"date={charge_date.isoformat()} amount=${amount}"
        )


if __name__ == '__main__':
    seed_data()
