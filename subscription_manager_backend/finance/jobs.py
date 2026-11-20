from contextlib import contextmanager

from django.core.management.base import BaseCommand
from django.utils import timezone

from .models import ScheduledJobStatus


@contextmanager
def track_job(name, *, dry_run=False):
    succeeded = False
    try:
        yield
        succeeded = True
    finally:
        if not dry_run:
            finished = timezone.now()
            values = {'last_finished_at': finished, 'succeeded': succeeded}
            if succeeded:
                values['last_succeeded_at'] = finished
            ScheduledJobStatus.objects.update_or_create(job=name, defaults=values)


class TrackedJobCommand(BaseCommand):
    def status_name(self, options):
        return self.job_name

    def execute(self, *args, **options):
        name = self.status_name(options)
        with track_job(name, dry_run=options.get('dry_run', False)):
            return super().execute(*args, **options)
