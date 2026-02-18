from datetime import date

from django.core.management.base import BaseCommand, CommandError

from subscriptions.services import BillingService


class Command(BaseCommand):
    help = "Record renewal charges for subscriptions due on a target date."

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            type=str,
            help="Charge date in YYYY-MM-DD format (defaults to today).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be recorded without writing transactions.",
        )

    def handle(self, *args, **options):
        target_date = date.today()
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
        self.stdout.write(f"Date: {results['date']}")
        self.stdout.write(f"Total due renewals: {results['total']}")
        self.stdout.write(f"Transactions created: {results['created']}")
        self.stdout.write(f"Already existing: {results['existing']}")
        self.stdout.write(f"Errors: {results['errors']}")
