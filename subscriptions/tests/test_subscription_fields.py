from django.test import TestCase
from django.contrib.auth import get_user_model
from subscriptions.models import Subscription
from datetime import date

User = get_user_model()

class SubscriptionAccountFieldsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='test@example.com', password='password')

    def test_create_subscription_with_account_fields(self):
        sub = Subscription.objects.create(
            user=self.user,
            service_name="Netflix",
            category="Streaming",
            billing_cycle="monthly",
            cost=15.00,
            start_date=date.today(),
            account_email="netflix_user@example.com",
            account_password="secretpassword123"
        )
        self.assertEqual(sub.account_email, "netflix_user@example.com")
        self.assertEqual(sub.account_password, "secretpassword123")

    def test_account_fields_are_optional(self):
        sub = Subscription.objects.create(
            user=self.user,
            service_name="Spotify",
            category="Streaming",
            billing_cycle="monthly",
            cost=10.00,
            start_date=date.today()
        )
        self.assertIsNone(sub.account_email)
        self.assertIsNone(sub.account_password)
