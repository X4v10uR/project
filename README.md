# DUES

DUES tracks recurring subscriptions, card spending, shared team expenses, and renewal reminders.

| Module | Stack | Local URL |
|---|---|---|
| `subscription_manager_frontend/` | React, TypeScript, Tailwind CSS, Vite | http://127.0.0.1:5173 |
| `subscription_manager_backend/` | Django, Django REST Framework, SQLite, Django Channels | http://127.0.0.1:8000 |

The frontend calls `/api/accounts/`, `/api/subscriptions/`, and `/api/dashboard/` using Django sessions and CSRF protection. Vite proxies API requests, avatars, uploaded media, and notification WebSockets to Django. The backend owns database migrations, Django admin, and notification emails. Its `legacy/` folder supports the original Django URLs and regression tests.

## Run locally on Windows

Use Python 3.11 and Node.js 20.19+ or 22.12+.

### Backend

From the repository root, in PowerShell:

```powershell
Set-Location subscription_manager_backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

For a new setup, copy `.env.example` to `.env` and put the generated values into `SECRET_KEY` and `ACCOUNT_PASSWORD_ENCRYPTION_KEY`.

```powershell
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
.\.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

For an existing installation, keep your `.env`, `db.sqlite3`, and any `media/` uploads in the backend folder. Keep your existing keys so encrypted subscription credentials remain readable. Relative SQLite paths in `DATABASE_URL` resolve from the backend folder.

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Run `.\.venv\Scripts\python.exe seed_demo.py` before starting the server if you want demo data in a fresh database. The demo email is `demo@subly.com` and the password is `demo1234`.

### Frontend

From the repository root, in another PowerShell terminal:

```powershell
Set-Location subscription_manager_frontend
npm ci
npm run dev
```

Open [DUES](http://127.0.0.1:5173). If Django is listening on a different address, copy the frontend's `.env.example` to `.env` and set `BACKEND_URL`.

## Checks

- From the backend folder, run `.\.venv\Scripts\python.exe manage.py check`, `.\.venv\Scripts\python.exe manage.py test`, and `node --test legacy/tests_js/*.test.cjs`.
- From the frontend folder, run `npm run build` for TypeScript checks and a production bundle in `dist/`.

GitHub Actions also runs Chromium against the built React app and a disposable Django database on pushes and pull requests. To run the browser tests locally, install backend dependencies, then run `npm run build`, `npx playwright install chromium`, and `npm run test:browser` from the frontend folder. Set `E2E_PYTHON` to the backend virtual environment’s Python executable if it is outside your PATH.

## Forecasts, budgets and payments

The dashboard lists every scheduled charge from today through the next 29 days. Quarterly plans renew every three calendar months. An optional trial end date sets the first paid date. A cancel-by date adds its own reminder using the subscription’s reminder settings.

Choose a dashboard currency to view its charge trend, adjust its balance, or set a monthly recurring spending limit. Personal and Teams have separate limits per currency. An in-app alert is created when the recurring monthly rate exceeds the limit. Returning within budget makes the next crossing eligible for another alert. Clear the spending limit and save to remove it.

Charge history starts each scheduled charge as **Scheduled**. The account holder or a team owner can mark it **Paid**, **Failed**, or **Refunded**, and mark each participant’s share reimbursed. New charges retain the split in effect when they are recorded. Use **Add historical share** to enter a known share on a charge recorded before the upgrade. The confirmed-paid total uses the recorded user share of each paid charge.

## Charge history and CSV import

Run the backend migrations before using charge history. History lists scheduled charges by renewal date, including charges for subscriptions removed after upgrading. Team history follows current team membership. Deleting a team removes its history.

Under Subscriptions, choose **Import CSV** to download a template or preview a DUES export. Review row errors and duplicates, then confirm. The importer matches personal subscriptions by service, plan, and account email, ignoring case. Imports create subscription schedules. Stored passwords, payment cards, and historical payments are excluded. New exports include participant shares and reminder settings.

For production routing and deployment, see the [frontend README](subscription_manager_frontend/README.md) and the [backend README](subscription_manager_backend/README.md).

## Planning and subscription reviews

Use **Quick add** for a four-field setup with common service presets. The full form keeps sharing, account details, and reminder options in expandable sections. **Planning**, in the navigation dock, contains spending insights, the renewal calendar, the review inbox, and shared settlements. Dashboard shortcuts also open these tools.

The Quick add and full create forms keep a save key when a response is lost, including across a refresh in the same tab. To retry, resubmit the same details. API clients can get the same protection by sending a version 4 UUID in `Idempotency-Key` on `POST /api/subscriptions/` and reusing that UUID only for retries of the same submission. A changed payload with the same key returns 409; a deleted outcome returns 410 rather than creating it again. The server keeps the account-scoped key, a keyed digest, and references to the result, not a copy of submitted form fields. An unkeyed request is treated as a separate operation.

The renewal calendar and its exports keep recorded **Scheduled** charges visible even after the billing job moves to the next renewal. Paid, failed, and refunded charge records are shown in History rather than forecast again.

Insights separate currencies, category commitments, recorded payments, remaining scheduled charges, and the next 12 months of renewals. Month comparisons show which services changed; the previous month depends on the charge history actually recorded. Calendar export downloads an all-day `.ics` file containing payments, trial endings, cancellation deadlines, and scheduled pauses/resumptions.

Subscriptions support six-month and 28-day cycles, introductory prices, and scheduled pause/resume dates. A pause skips charges while preserving the original billing cadence. Edit a subscription to record provider cancellation links, request/confirmation notes, and the last access date. Requested cancellations continue forecasting payments; confirming cancellation stops them. These tracking actions do not cancel or pause a provider account automatically.

The price-history panel records dated future changes, and editing the regular cost records a change effective today. Forecasts and newly recorded charges use the price effective on each charge date. Existing charge amounts and share snapshots are preserved. Fixed custom participant shares must fit within the regular and introductory prices. The review inbox surfaces imminent trials/deadlines, duplicates within a workspace, six-month review gaps, price changes, and low usage. Select subscriptions to preview savings by currency, pause tracking, or record a usage check-in.

Settlement balances aggregate shares on confirmed-paid charges by participant, payer, team, and currency. Team participants can link to current members. Partial repayments have an amount, note, timestamp, and recording user; overpayments are rejected. History reimbursement checkboxes remain available for shares without repayment records. CSV transfers lifecycle/introductory/pause settings, but does not transfer price-change history or repayment records.

DUES remains free, with a read-only plan summary. The dashboard's funding target is the recurring monthly commitment plus a chosen reserve; it is not a bank balance.

### Account security

In **Settings → Security**, verify your current password to set up optional authenticator MFA. Enter the setup key in your authenticator, confirm a code, and save the eight one-use recovery codes. MFA is required at sign-in, including legacy sign-in, and when re-verifying a password. Previously authenticated sessions must sign in again after enrollment. Reused authenticator codes are rejected; use a fresh code or an unused recovery code for another sensitive action.

Stored provider credentials require recent password verification, hide after one minute in the frontend, and are never included in normal subscription responses or CSV exports. The security activity list records sign-ins, password/email changes, MFA changes, recovery-code use, and credential updates/reveals. MFA secrets use the configured account-password encryption key; recovery codes are stored as hashes. Retain that encryption key when upgrading. Install the updated requirements and run migrations before starting the app.

Planning now includes connected-account discovery, private receipts, combined currency totals, detailed budgets, charge reports, live calendar subscriptions, notification preferences, portable backups, and subscription activity. Teams support Viewer and Accountant roles and separate Member credential access. See [finance setup](subscription_manager_backend/FINANCE_SETUP.md) for Plaid/Gmail credentials, optional image OCR, browser push, scheduling, and archive behavior.

New accounts can add a first bill, import a subscription list, or create a team from the dashboard. After adding a bill, the confirmation shows the next scheduled provider charge and links to its reminder settings.

**Needs attention** lists cancellation deadlines, expiring trials, price increases, and outstanding team renewal decisions for today through the next six days. Overdue team decisions stay visible for their renewal cycle. Open failed payments and pending owner approvals also appear. Each item links to the corresponding subscription, charge, or request. On the team page, owners can assign a renewal to an owner or member. The assignee or an owner can record a keep, change, or cancel decision for that billing date. Arrange any plan change or cancellation with the provider.

In **Planning → Connections**, preview a bank statement CSV, map its columns, and confirm outgoing payments. Reuse the same statement account label for duplicate detection. Use **Match manually** to link a payment to a same-currency charge, including team charges you manage as an owner or accountant. The confirmation shows both amounts and preserves the recorded charge and shares.

Receipt lists support merchant and receipt-date filters. Use **Load older** in Receipts or Activity to continue through the full history.

## Renewal decisions and charge differences

- In **Planning → Review inbox**, compare an eligible personal monthly subscription with a quoted annual or monthly price, or preview cancelling before the next unrecorded renewal. DUES compares scheduled payments over the same 12-month window. The preview assumes no immediate charge, credit or termination fee. It does not edit the subscription or contact the provider.
- In **Needs attention**, a confirmed same-currency statement CSV match can show the expected provider bill and the amount actually paid. Dismiss a one-off difference or open the subscription’s price history to record a recurring change yourself. The matching and original charge stay intact.
- In **Teams**, record paid and needed seats with a keep, change or cancel decision. The estimated savings assume an even price per seat; confirm the actual quote with the provider.

## Notification delivery

Operators can monitor failed or overdue jobs with `check_job_health` and restore the SQLite database and private receipts together with `recovery_snapshot`. See [scheduler monitoring and recovery](subscription_manager_backend/OPERATIONS.md).

Local email prints to the Django console by default. Start Django with `runserver` to enable local WebSocket updates in the same process. Set `REDIS_URL` when running multiple processes or when scheduled jobs need to broadcast to connected browser sessions.

Run notification commands from `subscription_manager_backend/`. Update the working directory of existing scheduled jobs to that folder. See [notification setup](subscription_manager_backend/NOTIFICATION_SETUP.md) for SMTP and scheduling instructions.
