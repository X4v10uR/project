import io
import sqlite3
from contextlib import closing
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core import mail
from django.core.management import call_command, CommandError
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from finance.models import ScheduledJobStatus
from finance.recovery import create_snapshot, restore_snapshot


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
