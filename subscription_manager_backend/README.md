# Subly Backend

Django and Django REST Framework API for Subly. This folder contains the database migrations, admin, renewal jobs, and avatar assets. The React app lives in [subscription_manager_frontend](../subscription_manager_frontend/).

## Run locally on Windows

Use Python 3.11 and open PowerShell in this repository.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Generate values for `SECRET_KEY` and `ACCOUNT_PASSWORD_ENCRYPTION_KEY` and save them in `.env`.

```powershell
.\.venv\Scripts\python.exe -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
.\.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

If you are moving an existing installation, copy its SQLite database, `.env`, and any uploads locally. Keep the existing keys so encrypted subscription credentials remain readable. Relative SQLite paths in `DATABASE_URL` resolve from this repository.

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

The API routes are under `/api/accounts/`, `/api/subscriptions/`, and `/api/dashboard/`. Django admin is at [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/). For the React UI, start the frontend separately and open [http://127.0.0.1:5173](http://127.0.0.1:5173).

## Checks

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test
```

The original Django page assets and browser scripts are in `legacy/`. Run their JavaScript tests with `node --test legacy/tests_js/dashboard_js.test.cjs`.

## Deployment

Set `SITE_URL` to the public frontend URL so invitations and renewal emails link to it. Serve the API, media, WebSockets, admin, and Django static assets where the frontend can reach them on the same origin. Run `python manage.py collectstatic --noinput` to collect Django assets, including the avatar SVGs.

Set `REDIS_URL` for live notifications across multiple processes or from scheduled jobs. See the [notification setup](NOTIFICATION_SETUP.md) for email and scheduling.

Run `python manage.py migrate` after upgrading. Existing balance adjustments remain in Personal; Teams keeps its own adjustment. Future subscriptions schedule their first charge on their start date. The migration preserves any first charge already recorded.

Before deleting an account that is a team's last owner, add another owner or delete that team. Teams with another owner retain their subscriptions and charge history when an account is deleted.
