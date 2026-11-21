import sqlite3
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connections

from finance.recovery import create_snapshot, restore_snapshot


class Command(BaseCommand):
    help = 'Back up the SQLite database and its private receipts together, or restore to a new directory.'
    requires_system_checks = []

    def add_arguments(self, parser):
        actions = parser.add_subparsers(dest='action', required=True)
        create = actions.add_parser('create')
        create.add_argument('destination', type=Path)
        restore = actions.add_parser('restore')
        restore.add_argument('snapshot', type=Path)
        restore.add_argument('destination', type=Path)

    def handle(self, **options):
        try:
            if options['action'] == 'create':
                db = connections['default']
                if db.vendor != 'sqlite':
                    raise CommandError('This snapshot command requires SQLite.')
                count = create_snapshot(Path(db.settings_dict['NAME']), Path(settings.PRIVATE_MEDIA_ROOT),
                                        options['destination'])
                action = 'Created snapshot'
            else:
                count = restore_snapshot(options['snapshot'], options['destination'])
                action = 'Restored database and receipts'
        except (OSError, ValueError, sqlite3.Error) as exc:
            raise CommandError(f'Recovery operation failed: {exc}') from exc
        self.stdout.write(f'{action} at {options["destination"]} ({count} private receipts).')
