import io
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from smtplib import SMTPException
from unittest.mock import patch

from django.core import mail
from django.core.management import call_command, CommandError
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from accounts.models import User
from finance.models import NotificationDelivery, NotificationPreference, ScheduledJobStatus
from finance.recovery import create_snapshot, restore_snapshot
from subscriptions.models import InAppNotification


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class JobHealthTests(TestCase):
    def check(self):
        call_command('check_job_health', '--job', 'finance_sync', '--email-to', 'ops@example.test', stdout=io.StringIO())

    def test_missing_late_failed_and_recovered(self):
        with self.assertRaisesMessage(CommandError, 'never reported'):
            self.check()
        old = timezone.now() - timedelta(hours=3)
        row = ScheduledJobStatus.objects.create(job='finance_sync', last_finished_at=old,
                                                last_succeeded_at=old, succeeded=True)
        with self.assertRaisesMessage(CommandError, 'last succeeded'):
            self.check()
        row.succeeded = False
        row.save()
        with self.assertRaisesMessage(CommandError, 'failed at'):
            self.check()
        self.assertEqual(len(mail.outbox), 1)
        row.succeeded = True
        row.last_succeeded_at = row.last_finished_at = timezone.now()
        row.save()
        self.check()
        self.check()
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn('healthy again', mail.outbox[-1].body)

    def test_unsent_alert_retries(self):
        with patch('finance.management.commands.check_job_health.send_mail', return_value=0):
            with self.assertRaisesMessage(CommandError, 'did not accept'):
                self.check()
        with self.assertRaisesMessage(CommandError, 'never reported'):
            self.check()
        self.assertEqual(len(mail.outbox), 1)

    def test_email_failures_mark_job_unhealthy_but_keep_retries_and_successful_sends(self):
        now = datetime(2026, 12, 1, 11, tzinfo=UTC)
        previous = now - timedelta(hours=1)
        status = ScheduledJobStatus.objects.create(job='finance_notifications', last_finished_at=previous,
                                                   last_succeeded_at=previous, succeeded=True)
        alert_user = User.objects.create_user('queued@example.test')
        digest_user = User.objects.create_user('digest@example.test')
        healthy_user = User.objects.create_user('healthy@example.test')
        pref = NotificationPreference.objects.create(user=digest_user, digest='daily',
                                                      last_digest_at=now - timedelta(days=1))
        with patch('django.utils.timezone.now', return_value=now - timedelta(minutes=1)):
            alert = InAppNotification.objects.create(recipient=alert_user, event_type='test', title='Queued alert')
            NotificationDelivery.objects.create(notification=alert, deliver_after=now, email=True)
            healthy = InAppNotification.objects.create(recipient=healthy_user, event_type='test', title='Successful alert')
            NotificationDelivery.objects.create(notification=healthy, deliver_after=now, email=True)
            InAppNotification.objects.create(recipient=digest_user, event_type='test', title='Digest alert')

        def send_alert(**fields):
            if fields['recipient_list'] == [alert_user.email]:
                raise SMTPException('Synthetic SMTP rejection')
            return mail.send_mail(**fields)

        with patch('django.utils.timezone.now', return_value=now), patch(
                'subscriptions.notifications.send_mail', side_effect=send_alert), patch(
                'finance.delivery.send_mail', return_value=0):
            with self.assertRaisesMessage(CommandError, '1 queued alert(s) and 1 digest(s)'):
                call_command('sync_finance', '--notifications-only', stdout=io.StringIO())
        status.refresh_from_db()
        self.assertFalse(status.succeeded)
        self.assertEqual(status.last_succeeded_at, previous)
        self.assertEqual(NotificationDelivery.objects.get(notification=alert).attempts, 1)
        self.assertFalse(NotificationDelivery.objects.filter(notification=healthy).exists())
        pref.refresh_from_db()
        self.assertEqual(pref.last_digest_at, now - timedelta(days=1))
        self.assertEqual([message.to for message in mail.outbox], [[healthy_user.email]])

        recovery = now + timedelta(minutes=11)
        with patch('django.utils.timezone.now', return_value=recovery):
            call_command('sync_finance', '--notifications-only', stdout=io.StringIO())
        status.refresh_from_db()
        self.assertTrue(status.succeeded)
        self.assertEqual(status.last_succeeded_at, recovery)
        self.assertFalse(NotificationDelivery.objects.exists())
        self.assertCountEqual([m.to for m in mail.outbox], [[healthy_user.email], [alert_user.email], [digest_user.email]])


class RecoveryTests(SimpleTestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.db = self.root / 'source.sqlite3'
        self.media = self.root / 'media'
        self.name = 'receipts/1/invoice'
        self.receipt = self.media / self.name
        self.receipt.parent.mkdir(parents=True)
        self.receipt.write_bytes(b'receipt bytes')
        self.snapshot = self.root / 'snapshot'
        self.restored = self.root / 'restored'
        with closing(sqlite3.connect(self.db)) as db:
            db.execute('CREATE TABLE finance_receipt (id INTEGER PRIMARY KEY, file TEXT NOT NULL)')
            db.execute('INSERT INTO finance_receipt VALUES (1, ?)', [self.name])
            db.commit()

    def test_restore_pair_with_integrity_and_no_overwrite(self):
        self.assertEqual(create_snapshot(self.db, self.media, self.snapshot), 1)
        self.receipt.unlink()
        self.db.unlink()
        self.assertEqual(restore_snapshot(self.snapshot, self.restored), 1)
        with closing(sqlite3.connect(self.restored / 'db.sqlite3')) as db:
            result, = db.execute('SELECT file FROM finance_receipt WHERE id=1').fetchone()
        self.assertEqual((self.restored / 'private_media' / result).read_bytes(), b'receipt bytes')
        with self.assertRaisesMessage(CommandError, 'new destination'):
            restore_snapshot(self.snapshot, self.restored)

    def test_missing_receipt_aborts_creation(self):
        self.receipt.unlink()
        with self.assertRaises(FileNotFoundError):
            create_snapshot(self.db, self.media, self.snapshot)
        self.assertFalse(self.snapshot.exists())

    def test_tampered_receipt_aborts_restore(self):
        create_snapshot(self.db, self.media, self.snapshot)
        (self.snapshot / 'private_media' / self.name).write_bytes(b'changed')
        with self.assertRaisesMessage(CommandError, 'checksums'):
            restore_snapshot(self.snapshot, self.restored)
        self.assertFalse(self.restored.exists())

    def test_snapshot_rejects_outside_receipt_reference(self):
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("UPDATE finance_receipt SET file = 'receipts/../../source.sqlite3'")
            db.commit()
        with self.assertRaisesMessage(CommandError, 'invalid receipt path'):
            create_snapshot(self.db, self.media, self.snapshot)
        self.assertFalse(self.snapshot.exists())
