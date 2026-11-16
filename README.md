# Subly - Subscription Management SaaS

A premium Subscription Management SaaS application built with Django and Tailwind CSS.

## Features
- **Authentication**: Secure email-based login and signup.
- **Subscription Tracker**: Add, edit, and delete your recurring services.
- **Dashboard**: Visualize your monthly/yearly spend and upcoming renewals.
- **Email Notifications**: Automated renewal reminders 3 days before subscription ends.
- **Time-Based Notifications**: Send reminders at the exact time subscriptions expire.
- **Service Icons**: Beautiful icons for popular services (Netflix, Spotify, etc.).
- **Responsive Design**: Premium look and feel, optimized for all devices.

## Tech Stack
- **Backend**: Django (Python)
- **Frontend**: Django Templates + Tailwind CSS (`django-tailwind` build pipeline)
- **Database**: SQLite (default)
- **Email**: SMTP support with HTML templates

## Project layout

- `subly/` holds project settings, URL routing, and server entry points.
- `accounts/` handles authentication, account settings, and team workflows.
- `subscriptions/` keeps subscription workflows, card endpoints, and list presentation in `views.py`, `card_views.py`, and `list_context.py`.
- `dashboard/` assembles dashboard data and handles in-app notifications.
- `templates/`, `static/`, and `theme/` contain page markup, browser scripts, and the Tailwind build.

## Setup Instructions

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure your local environment**

   Copy `.env.example` to `.env`. Run the commands below and paste their outputs into `SECRET_KEY` and `ACCOUNT_PASSWORD_ENCRYPTION_KEY`, respectively. The sample config uses SQLite and prints email to the console. See [notification setup](NOTIFICATION_SETUP.md) for SMTP configuration.

   ```bash
   python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

3. **Build Tailwind assets**

   Run these commands when changing templates or styles. A compiled stylesheet is included for local startup.

   ```bash
   npm --prefix theme/static_src ci
   npm --prefix theme/static_src run build
   ```

4. **Run Migrations**
   ```bash
   python manage.py migrate
   ```

5. **Seed demo data** (optional for local development)
   ```bash
   python seed_demo.py
   ```
   *Creates a demo user: `demo@subly.com` with password `demo1234` and sample subscriptions.*

6. **Start the Server**
   ```bash
   python manage.py runserver
   ```

7. **Access the App**
   Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.

## Credentials for Demo
- **Email**: `demo@subly.com`
- **Password**: `demo1234`

## 📧 Email Notification System

### Quick Test Setup

1. **Create Test Subscription**
   - Login to your account
   - Go to "Add Subscription"
   - Fill in details:
     - **Service**: Netflix Premium
     - **Category**: Streaming
     - **Cost**: 15.99
     - **Currency**: USD
     - **Billing Cycle**: Monthly
     - **Start Date**: January 2, 2026 (28 days ago)
     - **Renewal Time**: 9:00 PM (optional)
     - **Status**: Active

2. **Test Email Notifications**
   ```bash
   # Test without sending emails (dry run)
   python manage.py send_renewal_notifications --dry-run
   
   # Test for specific time (9:00 PM)
   python manage.py send_renewal_notifications --time 21:00 --dry-run
   
   # Send actual email
   python manage.py send_renewal_notifications --time 21:00
   ```

### Email Configuration

#### For Development (Console Output)
```env
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
```
Emails will appear in your terminal/console.

#### For Production (Gmail SMTP)
1. **Enable 2-Factor Authentication** on your Gmail account
2. **Generate App Password**:
   - Go to Google Account Settings
   - Security → 2-Step Verification → App passwords
   - Generate password for "Mail"
3. **Update .env file**:
   ```env
   EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
   EMAIL_HOST_USER=your-email@gmail.com
   EMAIL_HOST_PASSWORD=your-16-character-app-password
   ```

### Automated Scheduling

#### Windows Task Scheduler
1. Open Task Scheduler
2. Create Basic Task: "Subly Notifications"
3. Set trigger: Daily at 3:00 PM (or hourly for time-based)
4. Action: Start a program
5. Program: `python`
6. Arguments: `manage.py send_renewal_notifications`
7. Start in: `C:\path\to\your\project`

#### Linux/Mac Cron Job
```bash
# Run daily at 3 PM
0 15 * * * cd /path/to/project && python manage.py send_renewal_notifications

# Run hourly for time-based notifications
0 * * * * cd /path/to/project && python scheduler.py --time-based
```

### Email Features
- **Beautiful HTML Design**: Professional gradient design with service icons
- **Time-Based Reminders**: Notifications sent at exact subscription end time
- **Service Icons**: Automatic icons for 50+ popular services
- **Mobile Responsive**: Optimized for all email clients
- **Duplicate Prevention**: Smart tracking to avoid spam

### Testing Commands
```bash
# View subscriptions due for notification
python manage.py send_renewal_notifications --dry-run

# Test specific time window
python manage.py send_renewal_notifications --time 15:30 --dry-run

# Send notifications for different timeframe
python manage.py send_renewal_notifications --days-before 7

# Run automated scheduler
python scheduler.py

# Run time-based scheduler (matches subscription end times)
python scheduler.py --time-based
```

### Troubleshooting
- **No emails received**: Check spam folder and email credentials
- **Console backend**: Emails appear in terminal, not inbox
- **Wrong timing**: Verify subscription renewal dates and times
- **Gmail issues**: Ensure app password (not regular password) is used

For detailed email setup instructions, see `NOTIFICATION_SETUP.md`.
