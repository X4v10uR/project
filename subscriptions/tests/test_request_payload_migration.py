from importlib import import_module

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from accounts.models import Team, TeamMembership
from subscriptions.models import TeamSubscriptionRequest


User = get_user_model()
migration_module = import_module("subscriptions.migrations.0013_scrub_pending_request_passwords")


class TeamRequestPayloadMigrationTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="owner-migrate@example.com", password="password")
        self.member = User.objects.create_user(email="member-migrate@example.com", password="password")
        self.team = Team.objects.create(name="Migration Team", created_by=self.owner)
        TeamMembership.objects.create(team=self.team, user=self.owner, role=TeamMembership.ROLE_OWNER)
        TeamMembership.objects.create(team=self.team, user=self.member, role=TeamMembership.ROLE_MEMBER)

    def test_scrub_removes_pending_payload_password_only(self):
        pending_request = TeamSubscriptionRequest.objects.create(
            team=self.team,
            requested_by=self.member,
            status=TeamSubscriptionRequest.STATUS_PENDING,
            payload={
                "service_name": "Pending Service",
                "account_password": "remove-me",
            },
        )
        approved_request = TeamSubscriptionRequest.objects.create(
            team=self.team,
            requested_by=self.member,
            status=TeamSubscriptionRequest.STATUS_APPROVED,
            reviewed_by=self.owner,
            reviewed_at=timezone.now(),
            payload={
                "service_name": "Approved Service",
                "account_password": "keep-for-history",
            },
        )

        migration_module.scrub_pending_request_passwords(django_apps, None)

        pending_request.refresh_from_db()
        approved_request.refresh_from_db()
        self.assertNotIn("account_password", pending_request.payload)
        self.assertEqual(approved_request.payload.get("account_password"), "keep-for-history")

    def test_scrub_is_idempotent(self):
        pending_request = TeamSubscriptionRequest.objects.create(
            team=self.team,
            requested_by=self.member,
            status=TeamSubscriptionRequest.STATUS_PENDING,
            payload={
                "service_name": "Idempotent Service",
                "account_password": "remove-me-twice",
            },
        )

        migration_module.scrub_pending_request_passwords(django_apps, None)
        migration_module.scrub_pending_request_passwords(django_apps, None)

        pending_request.refresh_from_db()
        self.assertNotIn("account_password", pending_request.payload)
