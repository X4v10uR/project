import json
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from subscriptions.models import Card, Subscription

User = get_user_model()


class CardsApiTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email="cards@example.com", password="password")
        self.other_user = User.objects.create_user(email="other@example.com", password="password")
        self.client.force_login(self.user)

    def post_json(self, url, payload):
        return self.client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def test_state_endpoint_returns_expected_keys_and_user_data_only(self):
        Card.objects.create(
            user=self.user,
            nickname="My Card",
            last4="1111",
            brand="visa",
            theme="dark",
            is_primary=True,
        )
        Card.objects.create(
            user=self.other_user,
            nickname="Other Card",
            last4="2222",
            brand="mastercard",
            theme="navy",
            is_primary=True,
        )

        response = self.client.get(reverse("subscriptions:cards_api_state"))
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertTrue(payload["ok"])
        state = payload["state"]
        self.assertIn("cards", state)
        self.assertIn("subscriptions", state)
        self.assertIn("selectedCardId", state)
        self.assertIn("search", state)
        self.assertIn("addModalOpen", state)
        self.assertIn("editCardId", state)
        self.assertIn("deleteCardId", state)
        self.assertEqual(len(state["cards"]), 1)
        self.assertEqual(state["cards"][0]["nickname"], "My Card")

    def test_create_first_card_auto_sets_primary(self):
        response = self.post_json(
            reverse("subscriptions:cards_api_create"),
            {
                "nickname": "First Card",
                "last4": "1234",
                "brand": "visa",
                "theme": "dark",
                "isPrimary": False,
            },
        )
        self.assertEqual(response.status_code, 201)

        card = Card.objects.get(user=self.user, nickname="First Card")
        self.assertTrue(card.is_primary)

    def test_set_primary_endpoint_unsets_previous_primary(self):
        card_one = Card.objects.create(
            user=self.user,
            nickname="Card One",
            last4="1000",
            brand="visa",
            theme="dark",
            is_primary=True,
        )
        card_two = Card.objects.create(
            user=self.user,
            nickname="Card Two",
            last4="2000",
            brand="mastercard",
            theme="plum",
            is_primary=False,
        )

        response = self.post_json(
            reverse("subscriptions:cards_api_set_primary", args=[card_two.pk]),
            {},
        )
        self.assertEqual(response.status_code, 200)

        card_one.refresh_from_db()
        card_two.refresh_from_db()
        self.assertFalse(card_one.is_primary)
        self.assertTrue(card_two.is_primary)

    def test_update_endpoint_validates_payload(self):
        card = Card.objects.create(
            user=self.user,
            nickname="Card One",
            last4="3000",
            brand="visa",
            theme="dark",
            is_primary=True,
        )

        response = self.post_json(
            reverse("subscriptions:cards_api_update", args=[card.pk]),
            {
                "nickname": "",
                "last4": "12",
                "brand": "invalid-brand",
                "theme": "invalid-theme",
                "isPrimary": False,
            },
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertIn("nickname", payload["errors"])
        self.assertIn("last4", payload["errors"])
        self.assertIn("brand", payload["errors"])
        self.assertIn("theme", payload["errors"])

    def test_delete_with_move_reassigns_subscriptions(self):
        source_card = Card.objects.create(
            user=self.user,
            nickname="Source",
            last4="4444",
            brand="visa",
            theme="dark",
            is_primary=True,
        )
        target_card = Card.objects.create(
            user=self.user,
            nickname="Target",
            last4="5555",
            brand="amex",
            theme="navy",
            is_primary=False,
        )
        subscription = Subscription.objects.create(
            user=self.user,
            service_name="Netflix",
            category="Streaming",
            billing_cycle="monthly",
            cost=Decimal("12.99"),
            start_date=date.today(),
            status="active",
            card=source_card,
        )

        response = self.post_json(
            reverse("subscriptions:cards_api_delete", args=[source_card.pk]),
            {"move_to_card_id": target_card.pk},
        )
        self.assertEqual(response.status_code, 200)

        subscription.refresh_from_db()
        self.assertEqual(subscription.card_id, target_card.pk)
        self.assertFalse(Card.objects.filter(pk=source_card.pk).exists())

    def test_delete_without_move_detaches_subscriptions(self):
        card = Card.objects.create(
            user=self.user,
            nickname="Detachable",
            last4="6666",
            brand="discover",
            theme="rose",
            is_primary=True,
        )
        subscription = Subscription.objects.create(
            user=self.user,
            service_name="Spotify",
            category="Music",
            billing_cycle="monthly",
            cost=Decimal("9.99"),
            start_date=date.today(),
            status="active",
            card=card,
        )

        response = self.post_json(
            reverse("subscriptions:cards_api_delete", args=[card.pk]),
            {},
        )
        self.assertEqual(response.status_code, 200)

        subscription.refresh_from_db()
        self.assertIsNone(subscription.card_id)

    def test_cross_user_access_is_denied(self):
        other_card = Card.objects.create(
            user=self.other_user,
            nickname="Other",
            last4="7777",
            brand="visa",
            theme="dark",
            is_primary=True,
        )

        update_response = self.post_json(
            reverse("subscriptions:cards_api_update", args=[other_card.pk]),
            {
                "nickname": "Nope",
                "last4": "1234",
                "brand": "visa",
                "theme": "dark",
                "isPrimary": False,
            },
        )
        delete_response = self.post_json(
            reverse("subscriptions:cards_api_delete", args=[other_card.pk]),
            {},
        )
        primary_response = self.post_json(
            reverse("subscriptions:cards_api_set_primary", args=[other_card.pk]),
            {},
        )

        self.assertEqual(update_response.status_code, 404)
        self.assertEqual(delete_response.status_code, 404)
        self.assertEqual(primary_response.status_code, 404)


class CardsLegacyRouteTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email="legacy@example.com", password="password")
        self.client.force_login(self.user)

    def test_get_routes_redirect_to_modal_urls(self):
        card = Card.objects.create(
            user=self.user,
            nickname="Legacy",
            last4="8888",
            brand="visa",
            theme="dark",
            is_primary=True,
        )

        create_response = self.client.get(reverse("subscriptions:card_create"))
        update_response = self.client.get(reverse("subscriptions:card_update", args=[card.pk]))
        delete_response = self.client.get(reverse("subscriptions:card_delete", args=[card.pk]))

        self.assertRedirects(
            create_response,
            f"{reverse('subscriptions:card_list')}?modal=add",
            fetch_redirect_response=False,
        )
        self.assertRedirects(
            update_response,
            f"{reverse('subscriptions:card_list')}?modal=edit&card={card.pk}",
            fetch_redirect_response=False,
        )
        self.assertRedirects(
            delete_response,
            f"{reverse('subscriptions:card_list')}?modal=delete&card={card.pk}",
            fetch_redirect_response=False,
        )

    def test_post_legacy_create_still_works(self):
        response = self.client.post(
            reverse("subscriptions:card_create"),
            {"nickname": "Legacy Create", "last4": "9999", "brand": "Visa"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Card.objects.filter(user=self.user, nickname="Legacy Create").exists())

    def test_post_legacy_update_still_works(self):
        card = Card.objects.create(
            user=self.user,
            nickname="Legacy Old",
            last4="1234",
            brand="Visa",
            theme="dark",
            is_primary=True,
        )

        response = self.client.post(
            reverse("subscriptions:card_update", args=[card.pk]),
            {"nickname": "Legacy New", "last4": "1234", "brand": "Visa"},
        )
        self.assertEqual(response.status_code, 302)
        card.refresh_from_db()
        self.assertEqual(card.nickname, "Legacy New")

    def test_post_legacy_delete_detaches_subscriptions(self):
        card = Card.objects.create(
            user=self.user,
            nickname="Legacy Delete",
            last4="5678",
            brand="Visa",
            theme="dark",
            is_primary=True,
        )
        subscription = Subscription.objects.create(
            user=self.user,
            service_name="Delete Sub",
            category="Software",
            billing_cycle="monthly",
            cost=Decimal("5.00"),
            start_date=date.today(),
            status="active",
            card=card,
        )

        response = self.client.post(reverse("subscriptions:card_delete", args=[card.pk]))
        self.assertEqual(response.status_code, 302)
        subscription.refresh_from_db()
        self.assertIsNone(subscription.card_id)


class CardsPageSmokeTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email="smoke@example.com", password="password")
        self.client.force_login(self.user)

    def test_cards_page_embeds_bootstrap_state_and_js(self):
        response = self.client.get(reverse("subscriptions:card_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="cards-initial-state"', html=False)
        self.assertContains(response, "static/subscriptions/cards.js")
        self.assertContains(response, 'id="cards-app"', html=False)

    def test_sidebar_contains_cards_link(self):
        response = self.client.get(reverse("subscriptions:card_list"))
        self.assertContains(response, ">Cards<", html=False)
