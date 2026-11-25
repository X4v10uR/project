import csv
from datetime import timedelta
from io import StringIO
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Team, TeamMembership

from subscriptions.models import Card, Subscription, TeamSubscriptionRequest, Transaction


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

    def test_history_keeps_the_six_latest_charges_for_each_subscription(self):
        today = timezone.localdate()
        subscriptions = [
            Subscription.objects.create(
                user=self.user, service_name=name, cost='18.00', billing_cycle='monthly', start_date=today,
            )
            for name in ('Movies', 'Music')
        ]
        dates = [today - timedelta(days=offset) for offset in range(9)]
        Transaction.objects.bulk_create([
            Transaction(user=self.user, subscription=sub, charged_for_date=day, amount=sub.cost)
            for sub in subscriptions for day in dates
        ])
        portfolio = self.client.get(self.collection).json()
        for sub in subscriptions:
            history = portfolio['details'][str(sub.pk)]['history']
            self.assertEqual([entry['charged_for_date'] for entry in history], [day.isoformat() for day in dates[:6]])

        filtered = self.client.get(self.collection, {'q': 'Movies'}).json()
        self.assertEqual(list(filtered['details']), [str(subscriptions[0].pk)])
        self.assertEqual(filtered['stats'], portfolio['stats'])
        self.assertEqual(filtered['burn_metrics'], portfolio['burn_metrics'])

    def test_editing_returned_details_preserves_custom_participant_shares(self):
        payload = {**self.payload, 'split_type': 'custom', 'participants': [{'name': 'Alex', 'share': '7.25'}]}
        result = self.client.post(self.collection, payload, content_type='application/json')
        self.assertEqual(result.status_code, 201, result.content)
        url = reverse('subscriptions_api:detail', args=[result.json()['id']])
        fields = self.client.get(url).json()
        fields['notes'] = 'Updated the description'
        result = self.client.put(url, fields, content_type='application/json')
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(result.json()['participants'][0]['share_amount'], '7.25')
        self.assertEqual(result.json()['user_cost'], '10.75')

    def test_card_spending_and_subscription_details_follow_current_prices(self):
        today = timezone.localdate()
        card = Card.objects.create(user=self.user, nickname='Card', last4='0101')
        created = self.client.post(self.collection, {**self.payload, 'card': card.pk}, content_type='application/json')
        self.assertEqual(created.status_code, 201, created.content)
        pk = created.json()['id']
        detail_url = reverse('subscriptions_api:detail', args=[pk])
        change = self.client.post(f'{detail_url}prices/', {'cost': '24.00', 'effective_on': today.isoformat()},
                                  content_type='application/json')
        self.assertEqual(change.status_code, 201, change.content)

        card_url = reverse('subscriptions_api:cards')
        self.assertEqual(self.client.get(card_url).json()['state']['subscriptions'][0]['monthlyPrice'], 8)
        detail = self.client.get(detail_url).json()
        self.assertEqual(detail['details']['cost'], detail['current_cost'])
        self.assertEqual(detail['details']['user_cost'], detail['current_user_cost'])
        self.assertEqual([p['share_amount'] for p in detail['participants']], ['8.00', '8.00'])
        old_charge = Transaction.objects.get(subscription_id=pk)
        self.assertEqual(list(old_charge.shares.values_list('amount', flat=True)), [Decimal('6'), Decimal('6')])
        portfolio = self.client.get(self.collection).json()
        self.assertEqual(portfolio['details'][str(pk)], detail['details'])

        Subscription.objects.filter(pk=pk).update(pause_from=today)
        paused_card = self.client.get(card_url).json()['state']['subscriptions'][0]
        self.assertEqual(paused_card['monthlyPrice'], 0)
        self.assertIsNone(paused_card['daysLeft'])

        paused = self.client.get(self.collection, {'status': 'paused'}).json()
        self.assertEqual([sub['current_status'] for sub in paused['subscriptions']], ['paused'])
        self.assertEqual(paused['stats']['paused'], 1)

        Subscription.objects.filter(pk=pk).update(status='paused', pause_from=today - timedelta(days=7), resume_on=today)
        resumed = self.client.get(self.collection, {'status': 'active'}).json()
        self.assertEqual([sub['id'] for sub in resumed['subscriptions']], [pk])
        self.assertEqual(resumed['subscriptions'][0]['current_status'], 'active')
        self.assertEqual(resumed['stats']['active'], 1)
        self.assertEqual(Decimal(str(resumed['stats']['monthly_spend'])), Decimal('8'))
        self.assertEqual(Decimal(str(resumed['burn_metrics']['active_monthly_spend'])), Decimal('8'))
        self.assertEqual(self.client.get(self.collection, {'status': 'paused'}).json()['subscriptions'], [])
        self.assertEqual(self.client.get(card_url).json()['state']['subscriptions'][0]['monthlyPrice'], 8)

    def test_full_edit_reactivates_confirmed_cancellation(self):
        create = self.client.post(self.collection, self.payload, content_type='application/json')
        self.assertEqual(create.status_code, 201, create.content)
        url = reverse('subscriptions_api:detail', args=[create.json()['id']])
        fields = self.client.get(url).json()
        result = self.client.put(url, {**fields, 'cancellation_state': 'confirmed'}, content_type='application/json')
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(result.json()['status'], 'cancelled')
        fields = self.client.get(url).json()
        result = self.client.put(url, {**fields, 'notes': 'Keep record'}, content_type='application/json')
        self.assertEqual(result.json()['current_status'], 'cancelled')
        result = self.client.put(url, {**result.json(), 'status': 'active'}, content_type='application/json')
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(result.json()['current_status'], 'active')
        self.assertEqual(result.json()['cancellation_state'], 'none')

    def test_old_confirmed_plan_can_be_edited_and_paused(self):
        create = self.client.post(self.collection, self.payload, content_type='application/json')
        pk = create.json()['id']
        url = reverse('subscriptions_api:detail', args=[pk])
        Subscription.objects.filter(pk=pk).update(status='active', cancellation_state='confirmed')
        fields = self.client.get(url).json()
        self.assertEqual(fields['status'], 'cancelled')
        save = self.client.put(url, {**fields, 'notes': 'Still cancelled'}, content_type='application/json')
        self.assertEqual(save.json()['current_status'], 'cancelled')
        pause = self.client.post(f'{url}status/', {'status': 'paused'}, content_type='application/json')
        self.assertEqual(pause.status_code, 200, pause.content)
        self.assertEqual(self.client.get(url).json()['current_status'], 'paused')
        self.assertEqual(Subscription.objects.get(pk=pk).cancellation_state, 'none')

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

    def test_csv_accept_header_downloads_attachment_and_requires_a_session(self):
        url = reverse('subscriptions_api:export')
        response = self.client.get(url, HTTP_ACCEPT='text/csv')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Disposition'].startswith('attachment;'))
        self.assertIn('Service Name', next(csv.reader(StringIO(response.content.decode()))))

        self.client.logout()
        response = self.client.get(url, HTTP_ACCEPT='text/csv')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response['Content-Type'].split(';')[0], 'text/csv')
        self.assertIn('detail', next(csv.reader(StringIO(response.content.decode()))))

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
