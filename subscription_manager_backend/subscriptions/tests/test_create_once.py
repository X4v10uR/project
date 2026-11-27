from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from accounts.models import TeamMembership, User
from accounts.team_workflows import create_team
from subscriptions.api_views import subscriptions
from subscriptions.models import Subscription, SubscriptionCreationReceipt, TeamSubscriptionRequest, Transaction


URL = '/api/subscriptions/'
NOW = datetime(2026, 11, 27, 12, tzinfo=UTC)
INPUT = {'service_name': 'Synthetic replay', 'category': 'Software', 'billing_cycle': 'monthly',
         'cost': '30.00', 'start_date': NOW.date().isoformat(), 'currency': 'USD'}


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class SubscriptionCreationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('creator@example.test')
        self.client.force_login(self.user)
        self.key = str(uuid4())
        self.clock = patch('django.utils.timezone.now', return_value=NOW)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def submit(self, data=None, key=None):
        return self.client.post(URL, INPUT if data is None else data, content_type='application/json',
                                HTTP_IDEMPOTENCY_KEY=key or self.key)

    def test_replay_has_one_plan_one_charge_and_no_payload_snapshot(self):
        first = self.submit()
        replayed = self.submit(dict(reversed(list(INPUT.items()))))
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(replayed.status_code, 201)
        self.assertEqual(first.json(), replayed.json())
        self.assertEqual(replayed.headers['Idempotency-Replayed'], 'true')
        self.assertEqual(Subscription.objects.filter(user=self.user).count(), 1)
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 1)
        receipt = SubscriptionCreationReceipt.objects.get(user=self.user)
        self.assertEqual(receipt.subscription_id, first.json()['id'])
        self.assertNotIn(INPUT['service_name'], receipt.request_digest)

    def test_changed_payload_conflicts_but_new_key_allows_a_distinct_create(self):
        self.assertEqual(self.submit().status_code, 201)
        result = self.submit({**INPUT, 'cost': '40.00'})
        self.assertEqual(result.status_code, 409)
        self.assertEqual(result.json()['code'], 'idempotency_conflict')
        self.assertEqual(Subscription.objects.count(), 1)
        self.assertEqual(self.submit(key=str(uuid4())).status_code, 201)
        self.assertEqual(Subscription.objects.count(), 2)

    def test_signing_key_rotation_preserves_a_replay_and_refreshes_its_digest(self):
        with override_settings(SECRET_KEY='synthetic-previous-key', SECRET_KEY_FALLBACKS=[]):
            self.client.force_login(self.user)
            self.assertEqual(self.submit().status_code, 201)
            original = SubscriptionCreationReceipt.objects.get(user=self.user).request_digest

        with override_settings(SECRET_KEY='synthetic-current-key', SECRET_KEY_FALLBACKS=['synthetic-previous-key']):
            changed = self.submit({**INPUT, 'cost': '40.00'})
            self.assertEqual(changed.status_code, 409)
            self.assertEqual(SubscriptionCreationReceipt.objects.get(user=self.user).request_digest, original)
            replayed = self.submit()
            self.assertEqual(replayed.status_code, 201)
            self.assertEqual(replayed.headers['Idempotency-Replayed'], 'true')
            self.assertNotEqual(SubscriptionCreationReceipt.objects.get(user=self.user).request_digest, original)

        with override_settings(SECRET_KEY='synthetic-current-key', SECRET_KEY_FALLBACKS=[]):
            self.assertEqual(self.submit().headers['Idempotency-Replayed'], 'true')
        self.assertEqual(Subscription.objects.filter(user=self.user).count(), 1)
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 1)

    def test_key_is_scoped_to_user_and_invalid_submission_can_be_corrected(self):
        self.assertEqual(self.submit(key='invalid').status_code, 400)
        self.assertEqual(self.submit({**INPUT, 'cost': '-1.00'}).status_code, 400)
        self.assertFalse(SubscriptionCreationReceipt.objects.exists())
        first = self.submit()
        self.assertEqual(first.status_code, 201)
        other = User.objects.create_user('other-creator@example.test')
        self.client.force_login(other)
        result = self.submit()
        self.assertEqual(result.status_code, 201)
        self.assertNotEqual(result.json()['id'], first.json()['id'])
        self.assertEqual(SubscriptionCreationReceipt.objects.count(), 2)

    def test_a_deleted_result_never_recreates_subscription_or_charge(self):
        first = self.submit()
        pk = first.json()['id']
        self.assertEqual(self.client.delete(f'{URL}{pk}/').status_code, 204)
        self.assertEqual(self.submit().status_code, 410)
        self.assertFalse(Subscription.objects.exists())
        self.assertEqual(Transaction.objects.count(), 1)

    def test_team_request_replays_only_while_requester_can_access_the_team(self):
        owner = User.objects.create_user('team-owner@example.test')
        team = create_team(name='Studio team', user=owner)
        member = TeamMembership.objects.create(user=self.user, team=team, role='member')
        data = {**INPUT, 'team_id': team.pk}
        first = self.submit(data)
        self.assertEqual(first.status_code, 202, first.content)
        repeated = self.submit(data)
        self.assertEqual(repeated.status_code, 202)
        self.assertEqual(repeated.json(), first.json())
        self.assertEqual(TeamSubscriptionRequest.objects.count(), 1)
        member.delete()
        self.assertEqual(self.submit(data).status_code, 404)
        self.assertEqual(TeamSubscriptionRequest.objects.count(), 1)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class ConcurrentSubscriptionCreationTests(TransactionTestCase):
    def test_concurrent_same_key_has_one_outcome_on_retry(self):
        user = User.objects.create_user('concurrent@example.test')
        key = str(uuid4())
        barrier = Barrier(2)

        def submit(wait=False):
            request = APIRequestFactory().post(URL, INPUT, format='json', HTTP_IDEMPOTENCY_KEY=key)
            force_authenticate(request, user=user)
            if wait:
                close_old_connections()
                barrier.wait(timeout=5)
            try:
                return subscriptions(request)
            finally:
                if wait:
                    close_old_connections()

        with patch('django.utils.timezone.now', return_value=NOW):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(submit, True) for _ in range(2)]
                results = [future.result(timeout=10) for future in futures]
            self.assertIn(201, [result.status_code for result in results])
            for result in results:
                self.assertIn(result.status_code, (201, 503))
                if result.status_code == 503:
                    self.assertEqual(result['Retry-After'], '1')
            replay = submit()
        self.assertEqual(replay.status_code, 201)
        self.assertEqual(replay['Idempotency-Replayed'], 'true')
        self.assertEqual(Subscription.objects.filter(user=user).count(), 1)
        self.assertEqual(Transaction.objects.filter(user=user).count(), 1)
