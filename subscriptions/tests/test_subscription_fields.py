from cryptography.fernet import Fernet
from django.test import TestCase
from django.test import override_settings
from django.contrib.auth import get_user_model
from subscriptions.forms import SubscriptionForm
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
        self.assertNotEqual(sub.account_password, "secretpassword123")
        self.assertTrue(sub.account_password.startswith("enc::"))
        self.assertEqual(sub.get_account_password(), "secretpassword123")

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

    def test_edit_form_keeps_existing_password_when_blank(self):
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
        original_password_value = sub.account_password

        form = SubscriptionForm(
            data={
                'service_name': "Netflix",
                'category': "Streaming",
                'billing_cycle': "monthly",
                'cost': "15.00",
                'currency': "USD",
                'start_date': date.today().isoformat(),
                'renewal_time': "15:00",
                'status': "active",
                'reminders_enabled': "on",
                'card': "",
                'notes': "",
                'is_shared': "False",
                'split_type': "equal",
                'account_email': "netflix_user@example.com",
                'account_password': "",
            },
            instance=sub,
            user=self.user
        )
        self.assertTrue(form.is_valid(), form.errors)

        updated_sub = form.save()
        self.assertEqual(updated_sub.account_password, original_password_value)
        self.assertEqual(updated_sub.get_account_password(), "secretpassword123")

    def test_form_rejects_invalid_account_email(self):
        form = SubscriptionForm(
            data={
                'service_name': "Netflix",
                'category': "Streaming",
                'billing_cycle': "monthly",
                'cost': "15.00",
                'currency': "USD",
                'start_date': date.today().isoformat(),
                'renewal_time': "15:00",
                'status': "active",
                'reminders_enabled': "on",
                'card': "",
                'notes': "",
                'is_shared': "False",
                'split_type': "equal",
                'account_email': "invalid-email",
                'account_password': "",
            },
            user=self.user
        )

        self.assertFalse(form.is_valid())
        self.assertIn('account_email', form.errors)

    def test_encrypts_with_explicit_account_password_key(self):
        encryption_key = Fernet.generate_key().decode("utf-8")
        with override_settings(
            ACCOUNT_PASSWORD_ENCRYPTION_KEY=encryption_key,
            ACCOUNT_PASSWORD_LEGACY_FALLBACK=False,
        ):
            sub = Subscription.objects.create(
                user=self.user,
                service_name="Drive",
                category="Storage",
                billing_cycle="monthly",
                cost=5.00,
                start_date=date.today(),
                account_password="vault-secret",
            )

            self.assertTrue(sub.account_password.startswith("enc::"))
            self.assertNotIn("vault-secret", sub.account_password)
            self.assertEqual(sub.get_account_password(), "vault-secret")
