from datetime import timedelta
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from finance.models import Connection
from finance.connections import sync_connection, ProviderError
from finance.delivery import deliver_queued, send_digests
from finance.budgets import check_all


class Command(BaseCommand):
    help = 'Sync bank/mail accounts, deliver queued alerts/digests, and check detailed budgets.'

    def add_arguments(self, parser):
        parser.add_argument('--notifications-only', action='store_true')

    def handle(self, *args, **options):
        errors = 0
        if not options['notifications_only']:
            for connection in Connection.objects.filter(enabled=True):
                if connection.last_synced_at and connection.last_synced_at > timezone.now() - timedelta(hours=1):
                    continue
                try:
                    sync_connection(connection)
                    self.stdout.write(f'Synced connection {connection.pk} ({connection.provider})')
                except ProviderError:
                    errors += 1
                    self.stderr.write(f'Connection {connection.pk} needs attention in Connections.')
        check_all()
        self.stdout.write(f'Delivered {deliver_queued()} alerts and {send_digests()} digests.')
        if errors:
            raise CommandError(f'{errors} connection(s) could not sync.')
