#!/usr/bin/env python
"""
Subscription Renewal Notification Scheduler

This script can be run as a cron job to automatically send renewal notifications.
It supports time-based filtering to send notifications at the exact time subscriptions end.
It also records renewal charge transactions for subscriptions due through the current date.

Example cron jobs:
# Run every hour to check for time-specific notifications
0 * * * * cd /path/to/your/project && python scheduler.py --time-based

# Run daily at 3 PM for general notifications
0 15 * * * cd /path/to/your/project && python scheduler.py

For Windows Task Scheduler, create tasks that run this script at different times.
"""

import argparse
import logging
import os
import sys
from functools import partial

import django

# Add the project directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'subly.settings')
django.setup()

from django.core.management import call_command

from dashboard.budgets import check_budgets
from finance.jobs import track_job

logger = logging.getLogger(__name__)


def run_scheduler(*, time_based=False, days_before=None, dry_run=False):
    def budgets():
        with track_job('dashboard_budgets'):
            check_budgets()

    jobs = [('renewal_charges', partial(call_command, 'record_subscription_charges', dry_run=dry_run))]
    if not dry_run:
        jobs.extend([('dashboard_budgets', budgets), ('finance_sync', partial(call_command, 'sync_finance'))])
    jobs.append(('renewal_reminders', partial(call_command, 'send_renewal_notifications',
                 time_based=time_based, days_before=days_before, dry_run=dry_run)))

    failures = []
    for name, run in jobs:
        try:
            run()
            logger.info('Completed scheduled job %s', name)
        except Exception:
            failures.append(name)
            logger.exception('Scheduled job %s failed', name)
    if failures:
        logger.error('Scheduler completed with failures in %s', ', '.join(failures))
    else:
        logger.info('All scheduled jobs completed successfully')
    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser(description='Record charges, sync finance data and send reminders')
    parser.add_argument('--time-based', action='store_true', help='Use the current instant for timed reminders.')
    parser.add_argument('--days-before', type=int, help='Only process the selected reminder offset.')
    parser.add_argument('--dry-run', action='store_true', help='Preview billing and reminders without writing data.')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                        handlers=[logging.FileHandler('renewal_notifications.log'), logging.StreamHandler()])
    return run_scheduler(**vars(args))


if __name__ == '__main__':
    sys.exit(main())
