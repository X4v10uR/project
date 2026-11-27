# DUES

DUES tracks recurring subscriptions, card spending, shared team expenses, and renewal reminders.

## Table of contents

- [Project structure](#project-structure)
- [Run locally on Windows](#run-locally-on-windows)
  - [1. Install the prerequisites](#1-install-the-prerequisites)
  - [2. Get the project](#2-get-the-project)
  - [3. Install the backend dependencies](#3-install-the-backend-dependencies)
  - [4. Configure the backend environment](#4-configure-the-backend-environment)
  - [5. Initialize the database](#5-initialize-the-database)
  - [6. Start the backend server](#6-start-the-backend-server)
  - [7. Set up and start the frontend](#7-set-up-and-start-the-frontend)
  - [8. Open the app and sign in](#8-open-the-app-and-sign-in)
  - [Setup troubleshooting](#setup-troubleshooting)
- [Checks](#checks)
- [Forecasts, budgets and payments](#forecasts-budgets-and-payments)
- [Charge history and CSV import](#charge-history-and-csv-import)
- [Planning and subscription reviews](#planning-and-subscription-reviews)
  - [Account security](#account-security)
- [Renewal decisions and charge differences](#renewal-decisions-and-charge-differences)
- [Notification delivery](#notification-delivery)

## Project structure

| Module | Stack | Local URL |
|---|---|---|
| `subscription_manager_frontend/` | React, TypeScript, Tailwind CSS, Vite | http://127.0.0.1:5173 |
| `subscription_manager_backend/` | Django, Django REST Framework, SQLite, Django Channels | http://127.0.0.1:8000 |

The frontend calls `/api/accounts/`, `/api/subscriptions/`, and `/api/dashboard/` using Django sessions and CSRF protection. Vite proxies API requests, avatars, uploaded media, and notification WebSockets to Django. The backend owns database migrations, Django admin, and notification emails. Its `legacy/` folder supports the original Django URLs and regression tests.

## Run locally on Windows

These steps use Windows PowerShell. Run the backend and frontend in separate terminals, and keep both running while using the app.

### 1. Install the prerequisites

Install the following tools and make sure they are available in your terminal:

| Tool | Version / purpose |
|---|---|
| Git | To clone the repository |
| Python | 3.11, the version used in CI |
| Node.js and npm | Node.js 20.19+ on the 20.x line, or 22.12+; npm comes with Node.js |

Check your installation:

```powershell
git --version
python --version
node --version
npm --version
```

The default database is SQLite, so no separate database server is needed. Redis and external integration credentials are optional for local setup.

### 2. Get the project

Clone the repository and enter its root folder:

```powershell
git clone https://github.com/X4v10uR/project.git subscription_manager
Set-Location subscription_manager
```

If you already have the project, open PowerShell in its root folder instead. This is the folder containing this README and both `subscription_manager_backend/` and `subscription_manager_frontend/`.

### 3. Install the backend dependencies

From the repository root:

```powershell
Set-Location subscription_manager_backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The commands below use the virtual environment's Python executable directly, so you do not need to activate the environment.

### 4. Configure the backend environment

For a new installation, copy the example configuration and generate the two required keys. Continue in the backend folder:

```powershell
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
.\.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
notepad .env
```

In `.env`, set `SECRET_KEY` to the first command's generated key and `ACCOUNT_PASSWORD_ENCRYPTION_KEY` to the second command's generated key. Replace the placeholders below with those values, keep the other local defaults, and save the file:

```dotenv
DEBUG=True
SECRET_KEY="paste-the-generated-Django-secret-key"
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=sqlite:///db.sqlite3
SITE_URL=http://127.0.0.1:5173
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
ACCOUNT_PASSWORD_ENCRYPTION_KEY="paste-the-generated-Fernet-key"
```

Leave the optional Plaid, Gmail, browser push, and OCR settings at their example defaults unless you are setting up those integrations. See [finance setup](subscription_manager_backend/FINANCE_SETUP.md) for details.

For an existing installation, keep your existing `.env` and keys instead of copying the example or generating replacements. Preserve `db.sqlite3`, `media/`, and `private_media/` in the backend folder so your data and uploads remain available. Relative SQLite paths in `DATABASE_URL` resolve from the backend folder.

### 5. Initialize the database

Apply the migrations and check the backend configuration:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py check
```

The migration command creates `db.sqlite3` on a fresh installation.

Optionally, create an administrator account and follow the prompts:

```powershell
.\.venv\Scripts\python.exe manage.py createsuperuser
```

If you want sample subscriptions in a fresh local database, optionally run:

```powershell
.\.venv\Scripts\python.exe seed_demo.py
```

The demo email is `demo@subly.com` and the password is `demo1234`. Re-running this script resets that demo user's password, personal subscriptions, and related transactions.

### 6. Start the backend server

In the same backend terminal:

```powershell
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Leave this terminal open. Django now listens at [http://127.0.0.1:8000](http://127.0.0.1:8000). Local emails, including password-reset messages, print in this terminal with the default email configuration.

### 7. Set up and start the frontend

Open a second PowerShell terminal in the repository root:

```powershell
Set-Location subscription_manager_frontend
npm ci
Copy-Item .env.example .env
npm run dev
```

If the frontend already has a `.env`, keep it instead of running `Copy-Item`. The example sets `BACKEND_URL=http://127.0.0.1:8000`, matching the backend above. If Django uses a different address, update `BACKEND_URL` in the frontend `.env` before starting Vite.

Leave this terminal open too. Vite serves the React app at [http://127.0.0.1:5173](http://127.0.0.1:5173) and proxies API requests to Django.

### 8. Open the app and sign in

1. Open [DUES](http://127.0.0.1:5173) in your browser.
2. Choose **Sign up** to create an account, or sign in with the demo credentials if you loaded the sample data.
3. Add a subscription to check that the frontend can save data through the backend.
4. If you created an administrator account, sign in to [Django admin](http://127.0.0.1:8000/admin/) with that account.

Use `127.0.0.1` consistently for these local URLs. Press `Ctrl+C` in each terminal to stop its server. On later launches, start Django with the command in step 6 and run `npm run dev` from the frontend folder; the environment files and database persist.

### Setup troubleshooting

| Problem | What to check |
|---|---|
| Python, Node.js, npm, or Git is not recognized | Install the missing tool, ensure it is on PATH, and open a new terminal. |
| PowerShell says `npm.ps1` cannot be loaded | Use `npm.cmd` in place of `npm`, or run the npm commands in Command Prompt. |
| Django reports a missing `SECRET_KEY` or an invalid encryption key | Save both generated values in `subscription_manager_backend/.env` and restart Django. |
| Django reports missing database tables | Run the migration command in step 5 from the backend folder. |
| Vite reports an unsupported Node.js version | Use a Node.js version listed in step 1, then run `npm ci` again. |
| The frontend loads but sign-in or saving fails | Confirm Django is running, check the frontend's `BACKEND_URL`, and restart Vite after editing its `.env`. |
| Port 8000 or 5173 is already in use | Stop the other process using that port, then restart the server. |

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

Interactive editors compare their loaded revision when saving a subscription or scheduling a price. A stale save is rejected; reload and review the latest values before retrying. API clients can send the detail response's quoted `edit_revision` in `If-Match` to get the same protection; clients that omit the header retain the older behavior. Price amounts are never automatically converted when a currency changes: use a replacement plan if price history exists, or clear an old introductory offer first. Previously recorded charges retain their original currency.

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
