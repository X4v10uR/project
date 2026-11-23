# Scheduler monitoring and SQLite recovery

Run these commands from the backend directory with the same Django settings as the web service.

## Monitor scheduler health

Run the scheduler hourly. Set up a **separate** Task Scheduler task, cron entry, or monitoring service to run this check every 15 minutes with the backend working directory. A check inside the billing scheduler would stop at the same time as the scheduler. Use a host-level uptime check to cover a complete host outage.

```powershell
..\.venv\Scripts\python.exe manage.py check_job_health --max-age-minutes 120 --email-to ops@example.com
```

Replace the address with your operator mailbox and configure Django's SMTP backend for email delivery. Repeat `--email-to` for additional operators. Leaving out this option reports health on stdout/stderr and via the process exit status. A failed latest run, a missing first run, or a last success older than the threshold produces a nonzero exit. The default jobs are renewal charges, renewal reminders, dashboard budgets, and finance sync.

Operators receive an email when a job first becomes unhealthy and another on recovery. Repeated checks of the same outage continue to exit nonzero. Failed email deliveries retry on the next check. If you run individual commands on different schedules, select the jobs and tolerances for each check. For example, for the optional notifications-only finance job run `manage.py check_job_health --job finance_notifications --max-age-minutes 30 --email-to ops@example.com`. Start watching after the first scheduled run. Configure your monitor to report failures to execute the check itself, including database connection failures.

## Back up and restore SQLite with private receipts

Create the parent directory on an access-controlled backup volume. Each run needs a new destination. The example paths use the same virtual environment as the scheduler example.

```powershell
..\.venv\Scripts\python.exe manage.py recovery_snapshot create D:\DUESBackups\nightly-20261122
..\.venv\Scripts\python.exe manage.py recovery_snapshot restore D:\DUESBackups\nightly-20261122 D:\DUESBackups\rehearsal-20261122
```

Creation uses SQLite's online backup API, checks database integrity and foreign keys, and copies every private receipt referenced by that database snapshot. Concurrent uploads use unique filenames. If a referenced receipt is deleted or unreadable during the copy, creation fails before publishing the snapshot. Retry after resolving the missing file or quiescing writers. The manifest contains SHA-256 checksums of the database and all referenced receipts. Restore verifies those checksums and database integrity before publishing the recovered pair in the new directory. Existing destinations are refused.

The snapshot contains the entire application database, including accounts, grants, and encrypted credentials. Restrict filesystem access and encrypt your backup volume and off-site copies. Back up deployment secrets separately, including the original `SECRET_KEY` and `ACCOUNT_PASSWORD_ENCRYPTION_KEY`. Include public media uploads and deployment configuration in your host backup if your installation uses them.

For a rehearsal, use an isolated backend process with `DATABASE_URL` pointing to the recovered `db.sqlite3` and `PRIVATE_MEDIA_ROOT` pointing to its sibling `private_media` directory. Use the matching application version and keys, console email delivery, and disabled scheduled jobs. Sign in with a test account and download an identified receipt to confirm that both records and files are accessible. An automated isolated round trip runs with `manage.py test finance.test_operations`.

For recovery, stop the web processes and scheduled jobs, restore into a new directory, configure both paths together, and run `manage.py check` with the matching deployment settings. Verify a known receipt before resuming scheduled jobs. Retain the previous data directories and configuration until you have verified the recovered installation.
