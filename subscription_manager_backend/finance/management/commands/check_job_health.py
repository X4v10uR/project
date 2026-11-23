from datetime import timedelta
from smtplib import SMTPException

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone

from finance.models import JobHealthAlert, ScheduledJobStatus


HOURLY_JOBS = ('renewal_charges', 'renewal_reminders', 'dashboard_budgets', 'finance_sync')


def check_status(row, cutoff):
    if row is None:
        return 'has never reported a run'
    if not row.succeeded:
        return f'failed at {row.last_finished_at.isoformat()}'
    if row.last_succeeded_at is None:
        return 'has never reported success'
    if row.last_succeeded_at < cutoff:
        return f'last succeeded at {row.last_succeeded_at.isoformat()}'
    return None


@transaction.atomic
def notify_changes(recipient, jobs, issues):
    state, _ = JobHealthAlert.objects.select_for_update().get_or_create(recipient=recipient)
    previous = set(state.unhealthy_jobs)
    opened = sorted(set(issues) - previous)
    recovered = sorted(previous.intersection(jobs) - set(issues))
    if not opened and not recovered:
        return
    lines = [f'{name}: {issues[name]}' for name in opened]
    lines.extend(f'{name}: healthy again' for name in recovered)
    status = 'needs attention' if opened else 'recovery'
    if not send_mail(f'DUES scheduled jobs: {status}', '\n'.join(lines),
                     settings.DEFAULT_FROM_EMAIL, [recipient]):
        raise CommandError('The email backend did not accept the job health alert.')
    state.unhealthy_jobs = sorted(previous.difference(jobs).union(issues))
    state.save(update_fields=['unhealthy_jobs'])


class Command(BaseCommand):
    help = 'Check scheduler heartbeats and email operators on failure, overdue jobs, and recovery.'

    def add_arguments(self, parser):
        parser.add_argument('--max-age-minutes', type=int, default=120)
        parser.add_argument('--job', action='append', choices=(*HOURLY_JOBS, 'finance_notifications'))
        parser.add_argument('--email-to', action='append', help='Operator email address. Repeat for multiple recipients.')

    def handle(self, **options):
        age = options['max_age_minutes']
        if age < 1:
            raise CommandError('Choose a positive age in minutes.')
        jobs = set(options['job'] or HOURLY_JOBS)
        recipients = set(options['email_to'] or [])
        for address in recipients:
            try:
                validate_email(address)
            except ValidationError as exc:
                raise CommandError(f'Invalid operator address: {address}') from exc

        cutoff = timezone.now() - timedelta(minutes=age)
        rows = ScheduledJobStatus.objects.in_bulk(jobs)
        issues = {}
        for name in sorted(jobs):
            issue = check_status(rows.get(name), cutoff)
            if issue:
                issues[name] = issue
        messages = [f'{name}: {issue}' for name, issue in issues.items()]
        for address in sorted(recipients):
            try:
                notify_changes(address, jobs, issues)
            except (OSError, SMTPException, CommandError) as exc:
                messages.append(f'Alert for {address} failed: {exc}')
        if messages:
            raise CommandError('\n'.join(messages))
        self.stdout.write('All monitored scheduled jobs are healthy.')
