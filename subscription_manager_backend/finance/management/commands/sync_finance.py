from datetime import timedelta
from django.core.management.base import CommandError
from finance.jobs import TrackedJobCommand
from django.utils import timezone
from finance.models import Connection
from finance.connections import sync_connection, ProviderError
from finance.delivery import EmailDeliveryFailures, deliver_queued, send_digests
from finance.budgets import check_all


class Command(TrackedJobCommand):
    job_name = 'finance_sync'
    help = 'Sync bank/mail accounts, deliver queued alerts/digests, and check detailed budgets.'

    def status_name(self, options):
        return 'finance_notifications' if options['notifications_only'] else self.job_name

    def add_arguments(self, parser):
        parser.add_argument('--notifications-only', action='store_true')

    def handle(self, *args, **options):
        connection_errors = 0
        if not options['notifications_only']:
            for connection in Connection.objects.filter(enabled=True):
                if connection.last_synced_at and connection.last_synced_at > timezone.now() - timedelta(hours=1):
                    continue
                try:
                    sync_connection(connection)
                    self.stdout.write(f'Synced connection {connection.pk} ({connection.provider})')
                except ProviderError:
                    connection_errors += 1
                    self.stderr.write(f'Connection {connection.pk} needs attention in Connections.')
        check_all()
        failures = EmailDeliveryFailures()
        alerts = deliver_queued(email_failures=failures)
        digests = send_digests(email_failures=failures)
        self.stdout.write(f'Delivered {alerts} alerts and {digests} digests.')
        errors = []
        if connection_errors:
            errors.append(f'{connection_errors} connection(s) could not sync.')
        if failures.queued or failures.digests:
            errors.append(f'Email delivery failed for {failures.queued} queued alert(s) and {failures.digests} digest(s).')
        if errors:
            raise CommandError(' '.join(errors))
