from datetime import date, datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch
from zipfile import ZipFile
import json

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from finance.backup import build_archive, restore_archive
from finance.models import Activity
from subscriptions.models import PriceChange, Subscription, TeamRenewal
from subscriptions.services import next_billing_date
from .models import TeamMembership, User
from .team_workflows import create_team


class TeamRenewalTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user('owner@example.com')
        self.member = User.objects.create_user('member@example.com')
        self.team = create_team(name='Design', user=self.owner)
        self.assignee = TeamMembership.objects.create(user=self.member, team=self.team, role='member')
        self.day = timezone.localdate() + timedelta(days=6)
        self.sub = Subscription.objects.create(
            user=self.owner, team=self.team, service_name='Design software', cost=15,
            category='Software', billing_cycle='monthly', start_date=self.day,
            cancel_by_date=self.day - timedelta(days=2),
        )
        self.endpoint = reverse('accounts_api:team_renewal', args=[self.team.pk, self.sub.pk])

    def update(self, user, **values):
        self.client.force_authenticate(user)
        return self.client.patch(self.endpoint, values, format='json')

    def test_team_and_dashboard_agree_when_pause_begins_at_local_midnight(self):
        self.owner.timezone = 'Asia/Karachi'
        self.owner.save(update_fields=['timezone'])
        Subscription.objects.filter(pk=self.sub.pk).update(
            start_date=date(2026, 1, 1), pause_from=date(2026, 1, 2),
        )
        self.client.force_login(self.owner)
        personal = Subscription.objects.create(
            user=self.owner, service_name='Personal software', cost=9,
            category='Software', billing_cycle='monthly', start_date=date(2026, 1, 1),
            pause_from=date(2026, 1, 2),
        )
        with patch('django.utils.timezone.now', return_value=datetime(2026, 1, 1, 20, tzinfo=dt_timezone.utc)):
            dashboard = self.client.get('/api/dashboard/?scope=teams').json()
            overview = self.client.get('/api/accounts/teams/').json()
            detail = self.client.get(reverse('accounts_api:team_detail', args=[self.team.pk])).json()
            subscriptions = self.client.get('/api/subscriptions/?status=paused').json()
            subscription = self.client.get(f'/api/subscriptions/{personal.pk}/').json()
        self.assertEqual(dashboard['as_of_date'], '2026-01-02')
        self.assertEqual(dashboard['total_paused'], 1)
        self.assertEqual(overview['monthly_spend_by_currency'], {})
        self.assertEqual(overview['subscriptions'][0]['status'], 'paused')
        self.assertEqual(detail['subscriptions'][0]['status'], 'paused')
        self.assertEqual(subscriptions['stats']['paused'], 1)
        self.assertEqual(subscriptions['subscriptions'][0]['current_status'], 'paused')
        self.assertEqual(subscription['current_status'], 'paused')
        self.assertEqual(timezone.get_current_timezone_name(), 'UTC')

    def test_assigned_member_records_decision_for_one_renewal(self):
        result = self.update(self.owner, assignee_id=self.assignee.pk)
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(result.json()['due_on'], self.sub.cancel_by_date.isoformat())
        result = self.update(self.member, decision='cancel', renewal_date=self.day)
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(result.json()['decided_by'], self.member.email)
        self.assertEqual(self.update(self.member, decision='cancel', renewal_date=self.day).status_code, 200)
        self.assertEqual(Activity.objects.filter(action='renewal.review.updated').count(), 2)
        self.sub.refresh_from_db()
        self.assertTrue(self.sub.bills_on(self.day))
        following = self.sub.calculate_renewal_date(self.day + timedelta(days=1))
        Subscription.objects.filter(pk=self.sub.pk).update(renewal_date=following)
        self.assertEqual(self.update(self.member, decision='keep', renewal_date=self.day).status_code, 400)
        details = self.client.get(reverse('accounts_api:team_detail', args=[self.team.pk]))
        review = details.json()['subscriptions'][0]['renewal']
        self.assertEqual(review['assignee_id'], self.assignee.pk)
        self.assertEqual(review['renewal_date'], following.isoformat())
        self.assertEqual(review['decision'], '')
        self.assertIsNone(review['decided_at'])

    def test_seat_review_uses_the_scheduled_price_and_is_scoped_to_the_renewal(self):
        PriceChange.objects.create(subscription=self.sub, previous_cost=Decimal('15.00'),
                                   cost=Decimal('25.00'), effective_on=self.day)
        fields = dict(decision='change', renewal_date=self.day, paid_seats=10, needed_seats=6,
                      decision_reason='Four licenses are no longer used.')
        self.assertEqual(self.update(self.member, **fields).status_code, 403)
        self.assertEqual(self.update(self.owner, assignee_id=self.assignee.pk).status_code, 200)
        result = self.update(self.member, **fields)
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(result.json()['seat_savings'], '10.00')
        detail_url = reverse('accounts_api:team_detail', args=[self.team.pk])
        details = self.client.get(detail_url).json()['subscriptions'][0]['renewal']
        self.assertEqual((details['paid_seats'], details['needed_seats']), (10, 6))
        self.assertEqual(details['decision_reason'], fields['decision_reason'])
        activity = Activity.objects.filter(action='renewal.review.updated').last()
        self.assertEqual(activity.changes['decision_reason'], {'changed': True})
        self.assertNotIn(fields['decision_reason'], str(activity.changes))
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.cost, Decimal('15.00'))
        self.assertTrue(self.sub.bills_on(self.day))
        following = self.sub.calculate_renewal_date(self.day + timedelta(days=1))
        Subscription.objects.filter(pk=self.sub.pk).update(renewal_date=following)
        self.assertEqual(self.update(self.member, **fields).status_code, 400)
        review = self.client.get(detail_url).json()['subscriptions'][0]['renewal']
        self.assertEqual(review['decision_reason'], '')
        self.assertIsNone(review['paid_seats'])
        self.assertIsNone(review['seat_savings'])
        result = self.update(self.member, decision='keep', renewal_date=following)
        self.assertEqual(result.status_code, 200, result.content)
        self.assertIsNone(TeamRenewal.objects.get(subscription=self.sub).paid_seats)

    def test_seat_counts_validate_and_can_be_cleared(self):
        common = dict(decision='keep', renewal_date=self.day)
        for counts in ({'paid_seats': 10}, {'paid_seats': 10, 'needed_seats': None},
                       {'paid_seats': 0, 'needed_seats': 0}, {'paid_seats': 5, 'needed_seats': -1},
                       {'paid_seats': 5, 'needed_seats': 1_000_001}):
            with self.subTest(counts=counts):
                self.assertEqual(self.update(self.owner, **common, **counts).status_code, 400)
        self.assertEqual(self.update(self.owner, **common, decision_reason='a' * 501).status_code, 400)
        self.assertEqual(self.update(self.owner, decision='', renewal_date=self.day, decision_reason='No').status_code, 400)
        result = self.update(self.owner, **common, paid_seats=3, needed_seats=0, decision_reason='Unused')
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(result.json()['seat_savings'], '15.00')
        result = self.update(self.owner, **common, paid_seats=3, needed_seats=4)
        self.assertEqual(result.json()['seat_savings'], '0.00')
        self.assertEqual(result.json()['decision_reason'], 'Unused')
        result = self.update(self.owner, decision='', renewal_date=self.day)
        self.assertEqual(result.status_code, 200, result.content)
        review = TeamRenewal.objects.get()
        self.assertEqual(review.decision_reason, '')
        self.assertIsNone(review.paid_seats)
        self.assertIsNone(review.needed_seats)

    def test_assignment_and_decision_permissions_follow_membership(self):
        self.assertEqual(self.update(self.member, assignee_id=self.assignee.pk).status_code, 403)
        self.assertEqual(self.update(self.member, decision='keep', renewal_date=self.day).status_code, 403)
        other = User.objects.create_user('outsider@example.com')
        other_team = create_team(name='Other', user=other)
        foreign_member = other_team.memberships.get(user=other)
        self.assertEqual(self.update(self.owner, assignee_id=foreign_member.pk).status_code, 404)
        self.assertEqual(self.update(other, decision='keep', renewal_date=self.day).status_code, 404)
        self.assertFalse(TeamRenewal.objects.exists())
        self.update(self.owner, assignee_id=self.assignee.pk)
        role_endpoint = reverse('accounts_api:team_member', args=[self.team.pk, self.assignee.pk])
        self.assertEqual(self.client.patch(role_endpoint, {'role': 'viewer'}, format='json').status_code, 200)
        self.assertIsNone(TeamRenewal.objects.get().assignee_id)
        self.assertEqual(self.update(self.owner, assignee_id=self.assignee.pk).status_code, 404)
        self.assertEqual(self.update(self.member, decision='cancel', renewal_date=self.day).status_code, 403)
        self.assignee.role = 'member'
        self.assignee.save()
        self.update(self.owner, assignee_id=self.assignee.pk)
        self.assignee.delete()
        self.assertIsNone(TeamRenewal.objects.get().assignee_id)
        self.assertEqual(self.update(self.member, decision='keep', renewal_date=self.day).status_code, 404)

    def test_decision_and_owner_assignment_restore_to_new_team(self):
        owner_membership = self.team.memberships.get(user=self.owner)
        result = self.update(self.owner, assignee_id=owner_membership.pk, decision='change', renewal_date=self.day,
                             paid_seats=10, needed_seats=6, decision_reason='Use six seats.')
        self.assertEqual(result.status_code, 200, result.content)
        with ZipFile(BytesIO(build_archive(self.owner))) as archive:
            restore_archive(self.owner, archive, json.loads(archive.read('subly.json')))
        restored = TeamRenewal.objects.exclude(subscription=self.sub).get()
        self.assertEqual(restored.decision, 'change')
        self.assertEqual(restored.decision_for, self.day)
        self.assertEqual((restored.paid_seats, restored.needed_seats), (10, 6))
        self.assertEqual(restored.decision_reason, 'Use six seats.')
        self.assertEqual(restored.assignee.team_id, restored.subscription.team_id)
        self.assertNotEqual(restored.assignee_id, owner_membership.pk)
        self.assertEqual(restored.assignee.user_id, self.owner.pk)
        self.assertEqual(restored.decided_by_id, self.owner.pk)

    def test_missed_decision_deadline_stays_visible_until_renewal(self):
        today = timezone.localdate()
        deadline = today - timedelta(days=1)
        renewal = today + timedelta(days=14)
        Subscription.objects.filter(pk=self.sub.pk).update(
            start_date=renewal, renewal_date=renewal, cancel_by_date=deadline)
        self.client.force_login(self.owner)
        queue = self.client.get('/api/dashboard/?scope=teams').json()['needs_attention']
        self.assertEqual([(item['kind'], item['date']) for item in queue], [('decision', deadline.isoformat())])
        self.sub.refresh_from_db()
        next_cycle = self.sub.calculate_renewal_date(renewal + timedelta(days=1))
        Subscription.objects.filter(pk=self.sub.pk).update(renewal_date=next_cycle)
        self.assertEqual(self.client.get('/api/dashboard/?scope=teams').json()['needs_attention'], [])

    def test_next_billing_date_respects_pauses_and_cancellation(self):
        self.sub.pause_from = self.day
        self.assertIsNone(next_billing_date(self.sub, self.day))
        self.sub.resume_on = self.day + timedelta(days=35)
        self.assertEqual(next_billing_date(self.sub, self.day), self.sub.calculate_renewal_date(self.sub.resume_on))
        self.sub.cancellation_state = 'confirmed'
        self.assertIsNone(next_billing_date(self.sub, self.day))

    def test_stale_combined_update_preserves_assignment_decision_and_activity(self):
        fields = dict(assignee_id=self.assignee.pk, decision='change',
                      renewal_date=self.day - timedelta(days=1), paid_seats=5, needed_seats=3,
                      decision_reason='Stale proposal')
        result = self.update(self.owner, **fields)
        self.assertEqual(result.status_code, 400, result.content)
        self.assertIn('The renewal date changed.', str(result.json()))
        self.assertFalse(TeamRenewal.objects.filter(subscription=self.sub).exists())
        events = Activity.objects.filter(action='renewal.review.updated')
        self.assertFalse(events.exists())

        owner_membership = self.team.memberships.get(user=self.owner)
        self.assertEqual(self.update(self.owner, assignee_id=owner_membership.pk,
                                     decision='keep', renewal_date=self.day).status_code, 200)
        before = TeamRenewal.objects.filter(subscription=self.sub).values().get()
        self.assertEqual(self.update(self.owner, **fields).status_code, 400)
        self.assertEqual(TeamRenewal.objects.filter(subscription=self.sub).values().get(), before)
        self.assertEqual(events.count(), 1)
