# Finance tools and integration setup

The React app's **Planning** navigation now includes Budgets, Receipts, Reports,
Connections, Alert settings, Backup & restore, and Activity. Settings also links
to connected accounts, alert settings and data transfer. Subscription editing
links to receipts and change history; charge history links to charge receipts
and report export.

## Upgrade

From the backend directory, using the project's Python environment:

```powershell
..\.venv\Scripts\python.exe -m pip install -r requirements.txt
..\.venv\Scripts\python.exe manage.py migrate
```

Build the React frontend with `npm run build`. No paid service credentials are
needed for uploads, reports, backups, budgets, calendar feeds, activity, or saved
currency totals. Refreshing reference exchange rates contacts Frankfurter.

## Plaid bank connections

Set `PLAID_CLIENT_ID`, `PLAID_SECRET`, `PLAID_ENV=sandbox`, and
`PLAID_COUNTRY_CODES=US` in the backend `.env`. Restart Django. Production uses
`PLAID_ENV=production` and approved production credentials. Country codes and
institution coverage depend on your Plaid account; select countries it supports.
Enable the Transactions product in Plaid.

In **Connections**, verify your Subly password, select **Connect bank with
Plaid**, complete Link, then select **Sync now**. No bank login credentials pass
through Subly. Server-held Plaid access tokens are encrypted with the existing
account-password key. The adapter uses `/transactions/sync`, processes added,
modified and removed records, and commits the next cursor only after all pages
succeed. Concurrent syncs on one connection are rejected. An interrupted sync
claim expires after 30 minutes.

Discovery compares all available payment dates for each merchant and currency against calendar-month and fixed-day schedules. After at least two distinct dates fit a schedule, the suggestion shows the predicted payment after the latest import. Its editable start date preserves the inferred billing day across short months. These are suggestions, not
proof of a subscription. The user reviews editable details before adding one.
Suggested payment matches require the same normalized merchant, exact amount/currency,
and a date within three days of a personal scheduled charge. Confirming a match
marks the charge paid; imports never silently mark charges paid. A charge may
only be matched once. Pending and removed bank transactions are excluded.
For a different merchant name, amount, or date, choose **Match manually** on the imported payment and compare both amounts before confirming. The charge must use the payment currency. Team owners and accountants can also match eligible charges in their teams. History retains the scheduled amount and participant shares.

**Import a bank statement** in Connections accepts up to 500 rows per UTF-8 CSV (1 MB). Choose the account label, date format and debit sign, map the columns, and preview before confirming. Duplicate detection checks previous imports and restored records for the same statement account label. When a transaction ID is present, conflicting payment details for that ID appear as an error in the preview. Without an ID, rows with the same date, merchant, amount and currency count as duplicates. Supply distinct transaction IDs for legitimate identical payments.

Disconnect revokes the Plaid item before deleting local connection/import data.
Subscriptions, recorded charges and saved receipts remain.

Official references: [Plaid Link](https://plaid.com/docs/link/web/),
[Transactions Sync](https://plaid.com/docs/api/products/transactions/#transactionssync).

## Gmail receipt discovery

Create a Google OAuth web application, enable the Gmail API, configure its
consent screen/test users, and set:

```dotenv
GMAIL_CLIENT_ID=your-client-id
GMAIL_CLIENT_SECRET=your-client-secret
GMAIL_REDIRECT_URI=http://127.0.0.1:5173/api/finance/connections/gmail/callback/
```

Register exactly that redirect URI in Google. For a public deployment, use its
HTTPS origin for both this URI and `SITE_URL`. Public use of Gmail's read-only
scope may require Google's verification; development test users can connect
while the consent application is in testing.

Verify your password in **Connections**, select **Connect Gmail**, grant
read-only access, then sync. OAuth state is tied to the signed-in session and
expires after ten minutes. Offline refresh tokens are encrypted on the server.
The adapter never sends, deletes or modifies email.

Each sync scans at most 50 new messages from the last 90 days matching receipt,
invoice, subscription or renewal subjects. Later syncs skip captured messages
and continue the initial scan. Supported PDF/JPEG/PNG attachments are captured,
including messages whose amount appears only in a PDF. Message IDs prevent
duplicates, and partially completed attachment capture is resumed safely.
Amounts parsed from mail are unverified suggestions. Review them before adding
subscriptions or confirming payments. Disconnect revokes Google authorization
before removing the connection.

Official references: [Google web OAuth](https://developers.google.com/identity/protocols/oauth2/web-server),
[Gmail messages](https://developers.google.com/workspace/gmail/api/guides/list-messages).

## Private receipts and extraction

Receipt files are stored under `PRIVATE_MEDIA_ROOT` (default `private_media/`),
outside public `MEDIA_ROOT`. Keep this directory off public static/media routes.
Files are downloaded only through authenticated receipt endpoints. Team access
follows current membership. Owners and Accountants can upload/edit team
receipts; all current members can read them. Personal receipts stay private.

Uploads accept validated PDFs, PNGs and JPEGs up to 10 MB. PDFs must be
unencrypted and contain at most 50 pages. Text is extracted from the first 20
PDF pages. To extract text from image receipts, install Tesseract separately
and set `TESSERACT_CMD` to its executable's absolute path. OCR has a 30-second
timeout. Without Tesseract, images remain usable attachments with editable
metadata. Extracted dates/amounts always need review; they never change payment
status. Deleting a receipt or its owning account/team removes its private file.

## Reference currencies and detailed budgets

**Insights → Combined monthly spending** displays commitments in the selected
base currency. Refresh uses the public [Frankfurter v2 API](https://frankfurter.dev/).
Rate dates, sources, missing pairs and rates older than seven days are shown.
Totals with missing rates are explicitly labelled partial. Original currency
amounts and recorded payment history remain unchanged. Reference conversions
are estimates, not bank-settled amounts or historical conversion accounting.

Detailed budgets are separate from existing dashboard limits. Set a currency,
optional category, optional individual team, monthly limit and warning threshold
from 1–99%. Personal budgets use your share; team budgets use the full provider
price. Saving the same workspace/category/currency updates the limit. Alerts
fire when crossing the warning or full-limit threshold; dropping below a
threshold rearms it. The scheduler rechecks budgets as dated prices change.
Revoked/downgraded team access no longer exposes that team's budget spend.

## Email preferences, push, quiet hours and snoozing

**Alert settings** supports individual email alerts, daily or weekly summaries,
email opt-out, browser push and quiet hours in the user's profile timezone.
Quiet hours can cross midnight. In-app notifications remain available while
email/push delivery waits. Daily and weekly summaries replace individual alert
emails and run after 9 AM, outside quiet hours. Security password-reset emails
and explicit team invitations retain their dedicated delivery paths.

Generate VAPID keys once:

```powershell
..\.venv\Scripts\python.exe manage.py generate_push_keys
```

Put the resulting `VAPID_PUBLIC_KEY` and `VAPID_PRIVATE_KEY` in the backend
`.env`, set `VAPID_SUBJECT=mailto:your-real-contact@example.com`, and restart.
Keep the private key stable. Use HTTPS in production; localhost can be used for
development. The frontend serves `/notification-worker.js`,
`/manifest.webmanifest`, and `/subly-icon.svg`. It does not cache private pages.
Use **Enable on this browser** on each device; iOS requires a supported installed
Home Screen web app. Browser permission and platform support are required.
Logging out removes the current session's push subscription on the server.

**Remind me tomorrow** hides an unread notification for 24 hours, then queues a
reminder using the current delivery preferences. Queued delivery retries with
backoff up to ten attempts; worker errors are logged without provider secrets.

## Scheduling

See [operations](OPERATIONS.md) for independent stale-job alerts and a full SQLite/private-receipt backup and restore rehearsal.

Existing `scheduler.py` runs finance synchronization and queued/digest delivery
alongside renewal processing. Provider sync failures are logged without blocking
renewal reminders. Alternatively schedule these management commands yourself:

```powershell
# Every 5–15 minutes: deliver delayed/snoozed alerts, digests and budget checks.
..\.venv\Scripts\python.exe manage.py sync_finance --notifications-only
# Hourly: include bank and Gmail synchronization.
..\.venv\Scripts\python.exe manage.py sync_finance
```

The command skips accounts synced within the last hour. Use one scheduled job
per environment. Without a running job, on-demand sync works, but deferred
alerts, digest emails and unattended imports wait. Keep the existing renewal
charge/reminder jobs enabled too. No jobs are installed into the operating
system automatically.

Django admin → Finance → Scheduled job statuses shows each job’s last result, completion time, and last successful completion. Billing, dashboard budget checks, finance sync, and renewal reminders report independently. A failed job lets the scheduler finish the other jobs and makes it exit with status 1. Dry runs leave these timestamps unchanged. The standalone finance command records a separate status for notifications-only runs.

## Live calendars

**Renewal calendar → Create private calendar URL** issues a secret, revocable
subscription URL. Add it with “Subscribe by URL” in your calendar client.
Each request builds the current feed, including payment, trial, deadline,
pause and resume events. Team feeds respect current membership. The suggested
refresh interval is six hours; the calendar provider controls actual refresh.
Use a public HTTPS `SITE_URL` reachable by that provider. External providers
cannot fetch a localhost-only development server. Revoke a URL to return 404
on subsequent requests. Treat URLs as secrets; they are shown only at creation.

## Reports and portable backups

**Reports** downloads CSV or PDF charge history filtered by workspace, service,
dates and payment status. Reports include retained charges for deleted
subscriptions. They preserve currencies and escape spreadsheet formulas. A
report contains at most 10,000 charges; narrow the range for larger histories.

**Backup & restore** requires recent password verification and exports a ZIP
with subscriptions, personal cards, owned teams, history, splits, repayments,
price changes, receipts, budgets, balance settings, activity, notifications and
imported bank/mail payments. Auth/MFA secrets, provider-account passwords,
integration grants and calendar secrets are excluded. Backups contain sensitive
financial data; keep them private.

Restore first previews record counts, then requires explicit confirmation. It
adds new copies and never deletes existing subscriptions. Team names and member
snapshots are exported; restored teams initially contain only the restoring
user as Owner, and that user becomes payer of restored charges. Re-invite other
members explicitly. Participant names and repayment amounts remain historical
snapshots. Connections restore as archived ledgers with no access tokens; connect
providers again for live sync. Push remains off after restore. Existing balance
settings and notification preferences are restored for the current user.

All database changes are transactional; invalid references roll back the
restore and newly written receipt files are removed. Archives are limited to
110 MB compressed, 120 MB expanded and 50,000 records. Exported receipt content
is limited to 100 MB; large collections need separate receipt downloads.

## Team roles and activity

| Role | Subscription management | Payments, repayments, receipts, detailed team budgets | Stored credentials |
|---|---|---|---|
| Owner | Create/edit/delete, review requests, manage members | Read/write | Allowed |
| Member | Read and submit requests | Read | Owner can enable/disable |
| Accountant | Read | Read/write | Denied |
| Viewer | Read | Read | Denied |

Owners can change existing members' roles and Member credential access from
the team page, including promoting another Owner. The last Owner cannot be
demoted. Existing Member credential access is preserved on upgrade. Role checks
are enforced on APIs and legacy credential URLs, not just hidden UI controls.

**Activity** records subscription field/status/price changes, participant and
reminder changes, usage reviews, request approvals, payment changes, repayments,
receipt changes and permission changes from this release onward. Password
values are never logged, and free-text notes are represented as changed flags.
Historical activity predating this release is not reconstructed.

## Validation

The backend test suite covers scoped access, private downloads, PDF extraction,
archive round trips/rollback, exchange-rate completeness, budget thresholds,
calendar revocation, Plaid pagination/idempotence, Gmail attachment capture,
matching, concurrency and notification policies. Provider adapters use mocked
responses in tests. Real Plaid/Gmail/push delivery requires configured credentials
and an authorized account/device. Playwright covers the React workflows against
an isolated database and private-file directory.
