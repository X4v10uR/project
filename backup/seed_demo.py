import os
import django
import random
from datetime import date, timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'subly.settings')
django.setup()

from accounts.models import User
from subscriptions.models import Subscription

def seed_data():
    # Create a demo user
    demo_email = 'demo@subly.com'
    user, created = User.objects.get_or_create(email=demo_email)
    if created:
        user.set_password('demo1234')
        user.save()
        print(f"Created demo user: {demo_email}")

    # Sample subscriptions
    services = [
        ('Netflix', 'Streaming', 'monthly', 15.99),
        ('Spotify', 'Streaming', 'monthly', 9.99),
        ('AWS', 'Software', 'monthly', 45.50),
        ('GitHub', 'Software', 'monthly', 4.00),
        ('Gym', 'Health', 'monthly', 50.00),
        ('Adobe CC', 'Software', 'monthly', 52.99),
        ('Disney+', 'Streaming', 'yearly', 79.99),
        ('Internet', 'Utilities', 'monthly', 60.00),
        ('ChatGPT Plus', 'Software', 'monthly', 20.00),
    ]

    Subscription.objects.filter(user=user).delete()

    today = date.today()

    for name, cat, cycle, cost in services:
        # Random start date in the last few months
        days_ago = random.randint(30, 180)
        start_date = today - timedelta(days=days_ago)
        
        status = random.choice(['active', 'active', 'active', 'paused', 'cancelled'])
        
        sub = Subscription.objects.create(
            user=user,
            service_name=name,
            category=cat,
            billing_cycle=cycle,
            cost=cost,
            currency='USD',
            start_date=start_date,
            status=status,
            notes=f"Personal {name} subscription."
        )
        print(f"Created subscription: {name}")

if __name__ == '__main__':
    seed_data()
