from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from subscriptions.cards_state import normalize_primary_cards_for_user
from subscriptions.models import Card, Subscription
from datetime import date

User = get_user_model()

class CardModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='test@example.com', password='password')

    def test_create_valid_card(self):
        card = Card.objects.create(
            user=self.user,
            nickname="Test Card",
            last4="1234",
            brand="Visa"
        )
        self.assertEqual(str(card), "Test Card — Visa •••• 1234")
        self.assertEqual(card.theme, "dark")
        self.assertFalse(card.is_primary)

    def test_last4_validation_length(self):
        card = Card(
            user=self.user,
            nickname="Bad Card",
            last4="123" # too short
        )
        with self.assertRaises(ValidationError):
            card.full_clean()
        
        card.last4 = "12345" # too long
        with self.assertRaises(ValidationError):
            card.full_clean()

    def test_last4_validation_numeric(self):
        card = Card(
            user=self.user,
            nickname="Bad Card",
            last4="abcd" # not numeric
        )
        with self.assertRaises(ValidationError):
            card.full_clean()

    def test_create_card_without_brand(self):
        card = Card.objects.create(
            user=self.user,
            nickname="No Brand Card",
            last4="9999"
        )
        self.assertEqual(str(card), "No Brand Card •••• 9999")

    def test_associate_card_with_subscription(self):
        card = Card.objects.create(
            user=self.user,
            nickname="Sub Card",
            last4="5678"
        )
        sub = Subscription.objects.create(
            user=self.user,
            service_name="Netflix",
            category="Streaming",
            billing_cycle="monthly",
            cost=15.00,
            start_date=date.today(),
            card=card
        )
        self.assertEqual(sub.card, card)

    def test_card_deletion_does_not_delete_subscription(self):
        card = Card.objects.create(
            user=self.user,
            nickname="Temp Card",
            last4="0000"
        )
        sub = Subscription.objects.create(
            user=self.user,
            service_name="Spotify",
            category="Streaming",
            billing_cycle="monthly",
            cost=10.00,
            start_date=date.today(),
            card=card
        )
        
        card.delete()
        sub.refresh_from_db()
        self.assertIsNone(sub.card)
        self.assertTrue(Subscription.objects.filter(pk=sub.pk).exists())

    def test_only_one_primary_card_allowed_per_user(self):
        Card.objects.create(
            user=self.user,
            nickname="Primary One",
            last4="1111",
            brand="visa",
            is_primary=True,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Card.objects.create(
                    user=self.user,
                    nickname="Primary Two",
                    last4="2222",
                    brand="mastercard",
                    is_primary=True,
                )

    def test_primary_normalization_selects_newest_card_when_none_primary(self):
        older = Card.objects.create(
            user=self.user,
            nickname="Older",
            last4="3333",
            brand="visa",
            is_primary=False,
        )
        newer = Card.objects.create(
            user=self.user,
            nickname="Newer",
            last4="4444",
            brand="amex",
            is_primary=False,
        )

        normalize_primary_cards_for_user(self.user)

        older.refresh_from_db()
        newer.refresh_from_db()
        self.assertFalse(older.is_primary)
        self.assertTrue(newer.is_primary)

    def test_primary_normalization_keeps_existing_primary_card(self):
        older = Card.objects.create(
            user=self.user,
            nickname="Older",
            last4="5555",
            brand="visa",
            is_primary=True,
        )
        newer = Card.objects.create(
            user=self.user,
            nickname="Newer",
            last4="6666",
            brand="mastercard",
            is_primary=False,
        )

        normalize_primary_cards_for_user(self.user)

        older.refresh_from_db()
        newer.refresh_from_db()
        self.assertTrue(older.is_primary)
        self.assertFalse(newer.is_primary)
