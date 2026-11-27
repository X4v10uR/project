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

## Production security preflight

Run `python manage.py check --deploy --fail-level WARNING` against the protected production settings during release preparation. Do not put real credentials in CI variables used by tests. DUES adds checks for overlapping private receipt and public media/static roots, a missing or malformed credential encryption key, an invalid HTTPS site origin, insecure cookie overrides, and an unrestricted host list.

- Set `SITE_URL` to your full HTTPS origin and `ALLOWED_HOSTS` to the actual host names. Keep cookies marked Secure. Decide whether the ingress or Django owns the HTTP-to-HTTPS redirect and HSTS; if Django owns them, set `SECURE_SSL_REDIRECT` and an appropriate `SECURE_HSTS_SECONDS`. If the ingress owns them, verify both controls there and document any corresponding Django warnings you explicitly accept. Do not enable HSTS subdomain coverage or preload without confirming all affected hosts; document why you accept their warnings if you intentionally leave those options off. Trust forwarded protocol headers only when your ingress strips user-provided headers and sets the header itself.
- Keep `PRIVATE_MEDIA_ROOT`, database files, and backup volumes outside web-served paths. Serve intended public assets separately; never directly serve private receipts. Redact calendar, password-reset, and invite bearer paths from access logs and traces. Send production emails through a real configured mail backend, not the console. Limit uploads and concurrency at the ingress and protect admin access.
- Provision a dedicated Fernet `ACCOUNT_PASSWORD_ENCRYPTION_KEY`. Before replacing an existing key or turning off `ACCOUNT_PASSWORD_LEGACY_FALLBACK`, inventory and migrate legacy encrypted values under a controlled maintenance process and rehearse recovery. Historical credential encryption has a signing-key-derived fallback, and Django's `SECRET_KEY_FALLBACKS` does not replace a credential migration.
- During a controlled Django signing-key rollover, keep the outgoing key temporarily in the comma-separated secret setting `SECRET_KEY_FALLBACKS` on all workers. The subscription-create replay check accepts valid request digests under those keys and refreshes a verified older digest after authorized replay. After the supported retry and session window, remove expired keys. Signing keys that have been compromised require incident handling, not routine fallback retention. Do not purge create receipts casually: removing a receipt can let a previously saved operation be created again. Portable exports are copies and do not include replay receipts; SQLite operator snapshots do.
- Treat the portable ZIP as sensitive, even with credentials excluded. It can contain receipts, payments, and team information. Encrypt off-site copies, set retention, and restrict access. SHA-256 snapshot manifests detect corruption, not provenance.

The separate **Dependency audit** workflow checks the Python requirements and npm lockfile on dependency changes and weekly. Resolve advisories by updating the relevant dependency and running tests; do not silently ignore scan failures. The Python report covers the selected compatible resolution, not every possible installation from the requirements ranges. Verify dependencies from the actual release environment too.
