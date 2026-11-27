from datetime import date

from django.core.management.base import CommandError
from finance.jobs import TrackedJobCommand

from subscriptions.services import BillingService


class Command(TrackedJobCommand):
    job_name = 'renewal_charges'
    help = "Record renewal charges for subscriptions due on a target date."

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            type=str,
            help="Charge date in YYYY-MM-DD format (defaults to each payer’s local date).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be recorded without writing transactions.",
        )

    def handle(self, *args, **options):
        target_date = None
        input_date = options.get("date")
        if input_date:
            try:
                target_date = date.fromisoformat(input_date)
            except ValueError as exc:
                raise CommandError(
                    f"Invalid --date value '{input_date}'. Use YYYY-MM-DD format."
                ) from exc

        results = BillingService.record_renewal_charges(
            target_date=target_date,
            dry_run=options["dry_run"],
        )

        mode_label = "DRY RUN" if options["dry_run"] else "LIVE RUN"
        self.stdout.write(self.style.SUCCESS(f"[{mode_label}] Renewal charge processing"))
        date_label = results['date'] if target_date else f"payer-local (UTC run date: {results['date']})"
        self.stdout.write(f"Date: {date_label}")
        self.stdout.write(f"Total due renewals: {results['total']}")
        self.stdout.write(f"Transactions created: {results['created']}")
        self.stdout.write(f"Already existing: {results['existing']}")
        self.stdout.write(f"Errors: {results['errors']}")
        if results['errors']:
            raise CommandError(f"{results['errors']} renewal charge(s) failed.")
