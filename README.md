# Subly

Subly tracks recurring subscriptions, card spending, shared team expenses, and renewal reminders.

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

Open [Subly](http://127.0.0.1:5173). If Django is listening on a different address, copy the frontend's `.env.example` to `.env` and set `BACKEND_URL`.

## Checks

- From the backend folder, run `.\.venv\Scripts\python.exe manage.py check`, `.\.venv\Scripts\python.exe manage.py test`, and `node --test legacy/tests_js/dashboard_js.test.cjs`.
- From the frontend folder, run `npm run build` for TypeScript checks and a production bundle in `dist/`.

GitHub Actions runs both sets of checks on pushes and pull requests.

For production routing and deployment, see the [frontend README](subscription_manager_frontend/README.md) and the [backend README](subscription_manager_backend/README.md).

## Notifications

Local email prints to the Django console by default. Start Django with `runserver` to enable local WebSocket updates in the same process. Set `REDIS_URL` when running multiple processes or when scheduled jobs need to broadcast to connected browser sessions.

Run notification commands from `subscription_manager_backend/`. Update the working directory of existing scheduled jobs to that folder. See [notification setup](subscription_manager_backend/NOTIFICATION_SETUP.md) for SMTP and scheduling instructions.
