import csv
from io import StringIO
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Team, TeamMembership

from subscriptions.models import Card, Subscription, TeamSubscriptionRequest


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class SubscriptionApiTest(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(email='api@example.com', password='example-password')
        self.client.force_login(self.user)
        self.collection = reverse('subscriptions_api:list')
        self.payload = {
            'service_name': 'Video plan',
            'category': 'Streaming',
            'billing_cycle': 'monthly',
            'cost': '18.00',
            'start_date': timezone.localdate().isoformat(),
            'account_password': 'private-plan-password',
            'reminder_offsets': [1, 7],
            'is_shared': True,
            'participants': [{'name': 'Alex'}, {'name': 'Morgan'}],
        }

    def test_crud_reuses_shares_reminders_and_password_handling(self):
        response = self.client.post(self.collection, self.payload, content_type='application/json')
        self.assertEqual(response.status_code, 201, response.content)
        created = response.json()
        self.assertEqual(created['user_cost'], '6.00')
        self.assertCountEqual(created['reminder_offsets'], [1, 7])
        self.assertTrue(created['has_password'])
        self.assertNotIn('account_password', created)

        detail = reverse('subscriptions_api:detail', args=[created['id']])
        detail_response = self.client.get(detail)
        self.assertEqual(detail_response.status_code, 200, detail_response.content)
        self.assertIn('history', detail_response.json()['details'])

        response = self.client.put(
            detail,
            {**self.payload, 'cost': '20.00', 'account_password': '', 'is_shared': False, 'reminder_offsets': [3], 'currency': 'USD', 'status': 'paused', 'split_type': 'equal'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        subscription = Subscription.objects.get(pk=created['id'])
        self.assertEqual(subscription.user_cost, Decimal('20.00'))
        self.assertFalse(subscription.participants.exists())
        self.assertEqual(subscription.get_account_password(), self.payload['account_password'])
        self.assertEqual(response.json()['reminder_offsets'], [3])

        filtered = self.client.get(self.collection, {'status': 'active'})
        self.assertEqual(filtered.json()['subscriptions'], [])
        self.assertEqual(filtered.json()['stats']['paused'], 1)
        self.assertEqual(self.client.delete(detail).status_code, 204)
        self.assertFalse(Subscription.objects.filter(pk=created['id']).exists())

    def test_team_member_submits_request_without_saving_credentials(self):
        owner = get_user_model().objects.create_user(email='owner@example.com', password='example-password')
        team = Team.objects.create(name='API team', created_by=owner)
        TeamMembership.objects.create(team=team, user=owner, role=TeamMembership.ROLE_OWNER)
        TeamMembership.objects.create(team=team, user=self.user, role=TeamMembership.ROLE_MEMBER)
        response = self.client.post(self.collection, {**self.payload, 'team_id': team.pk}, content_type='application/json')
        self.assertEqual(response.status_code, 202, response.content)
        pending = TeamSubscriptionRequest.objects.get(pk=response.json()['request_id'])
        self.assertNotIn('account_password', pending.payload)
        self.assertFalse(team.subscriptions.exists())

    def test_equal_split_allocates_every_cent_and_preserves_password_input(self):
        password = '  enc::custom-password  '
        response = self.client.post(
            self.collection, {**self.payload, 'cost': '10.00', 'account_password': password},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201, response.content)
        item = response.json()
        self.assertEqual(item['user_cost'], '3.34')
        self.assertEqual([person['share_amount'] for person in item['participants']], ['3.33', '3.33'])
        self.assertEqual(Subscription.objects.get(pk=item['id']).get_account_password(), password)

    def test_new_subscription_uses_account_currency_when_omitted(self):
        self.user.preferred_currency = 'EUR'
        self.user.save(update_fields=['preferred_currency'])
        response = self.client.post(self.collection, self.payload, content_type='application/json')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['currency'], 'EUR')

    def test_invalid_values_return_bad_request_without_saving_subscription(self):
        for field, value in (
            ('cost', '-0.01'), ('currency', '=11'), ('start_date', '9999-12-31'),
            ('account_password', '🔑' * 80),
        ):
            with self.subTest(field=field):
                response = self.client.post(
                    self.collection, {**self.payload, field: value}, content_type='application/json',
                )
                self.assertEqual(response.status_code, 400, response.content)
                self.assertIn(field, response.json())
        self.assertFalse(Subscription.objects.exists())

    def test_export_neutralizes_formula_in_preexisting_currency(self):
        response = self.client.post(self.collection, self.payload, content_type='application/json')
        Subscription.objects.filter(pk=response.json()['id']).update(currency='=11')
        result = self.client.get(reverse('subscriptions_api:export'))
        exported = next(csv.DictReader(StringIO(result.content.decode())))
        self.assertEqual(exported['Currency'], "'=11")

    def test_card_state_does_not_expose_team_subscriptions_after_removal(self):
        owner = get_user_model().objects.create_user(email='owner@example.com')
        team = Team.objects.create(name='API team', created_by=owner)
        membership = TeamMembership.objects.create(team=team, user=self.user, role=TeamMembership.ROLE_MEMBER)
        card = Card.objects.create(user=self.user, nickname='Card', last4='0101', is_primary=True)
        sub = Subscription.objects.create(
            user=owner, team=team, card=card, service_name='Team service', category='Software',
            billing_cycle='monthly', cost=Decimal('10.00'), start_date=timezone.localdate(),
        )
        url = reverse('subscriptions_api:cards')
        self.assertEqual(self.client.get(url).json()['state']['subscriptions'][0]['id'], f's{sub.pk}')
        membership.delete()
        self.assertEqual(self.client.get(url).json()['state']['subscriptions'], [])

    def test_card_reassignment_preserves_subscription(self):
        card = Card.objects.create(user=self.user, nickname='Source', last4='0101', is_primary=True)
        dest = Card.objects.create(user=self.user, nickname='Destination', last4='0202')
        response = self.client.post(self.collection, {**self.payload, 'card': card.pk}, content_type='application/json')
        self.assertEqual(response.status_code, 201, response.content)
        subscription_id = response.json()['id']

        response = self.client.delete(
            reverse('subscriptions_api:card_detail', args=[card.pk]),
            {'move_to_card_id': dest.pk},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(Subscription.objects.get(pk=subscription_id).card_id, dest.pk)
        self.assertTrue(response.json()['state']['cards'][0]['isPrimary'])
