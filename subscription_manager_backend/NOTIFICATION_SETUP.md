# 📧 Email Notification System Setup

This guide explains how to set up and use the subscription renewal notification system in DUES.

## 🎯 Features

- Renewals, first paid dates and cancel-by deadlines use the reminder offsets on each subscription. The default is three days.
- The hourly job uses each recipient’s profile time zone. After downtime it sends the most recent due reminder for each upcoming event on the next successful run.
- **Beautiful HTML Emails**: Professional-looking emails with service icons and branding
- **Duplicate Prevention**: System tracks sent notifications to avoid spam
- **Flexible Scheduling**: Can be run manually or scheduled as a cron job/task
- **Dry Run Mode**: Test notifications without actually sending emails
- **Optional Time Field**: Users can specify exact renewal time, defaults to 3:00 PM if not set

## ⚙️ Configuration

### 1. Email Settings

Update your `.env` file with email configuration:

```env
# For Development (emails appear in console)
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend

# For Production (using Gmail SMTP)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=your-email@gmail.com
ACCOUNT_PASSWORD_ENCRYPTION_KEY=your-generated-fernet-key

# Notification Settings
NOTIFICATION_DAYS_BEFORE=3
SITE_URL=https://your-domain.com
```

For implicit SSL, set `EMAIL_PORT=465`, `EMAIL_USE_SSL=True`, and `EMAIL_USE_TLS=False`.
The default port is 465 with SSL and 587 otherwise. `EMAIL_TIMEOUT` defaults to
15 seconds. Use a sender address your SMTP provider permits.

Team renewal reminders are sent individually. Successful recipients are recorded
even if another address fails; subsequent runs retry only the failed recipients.
Individual alert emails and summaries also retry when a backend accepts no message.

### 2. Gmail Setup (for Production)

1. Enable 2-Factor Authentication on your Gmail account
2. Generate an App Password:
   - Go to Google Account settings
   - Security → 2-Step Verification → App passwords
   - Generate password for "Mail"
3. Use the generated password in `EMAIL_HOST_PASSWORD`

## 🚀 Usage

### Manual Commands

```bash
# Send notifications (dry run to test)
python manage.py send_renewal_notifications --dry-run

# Send actual notifications
python manage.py send_renewal_notifications

# Send notifications for subscriptions ending at specific time
python manage.py send_renewal_notifications --time 09:00 --dry-run
python manage.py send_renewal_notifications --time 15:30 --dry-run

# Send notifications for different timeframe
python manage.py send_renewal_notifications --days-before 7
```

### Automated Scheduling

#### Option 1: Time-Based Scheduler (Recommended for Precise Timing)

```bash
# Run every hour to check for time-specific notifications
python scheduler.py --time-based
```

#### Option 2: General Scheduler

```bash
# Run once daily for all subscriptions
python scheduler.py
```

#### Option 3: Django Management Command

```bash
python manage.py send_renewal_notifications
```

## 📅 Setting Up Automated Scheduling

### Windows Task Scheduler (Hourly for Time-Based)

1. Open Task Scheduler
2. Create Basic Task: "DUES Hourly Notifications"
3. Set trigger: Daily, repeat every 1 hour for 24 hours
4. Action: Start a program
5. Program: `python`
6. Arguments: `scheduler.py --time-based`
7. Start in: `C:\path\to\subscription_manager\subscription_manager_backend`

### Windows Task Scheduler (Daily for General)

1. Create Basic Task: "DUES Daily Notifications"
2. Set trigger: Daily at 3:00 PM
3. Action: Start a program
4. Program: `C:\path\to\subscription_manager\subscription_manager_backend\run_notifications.bat`

The batch launcher uses the backend's `.venv`, falling back to a repository-level `.venv` or `python` on PATH. Arguments such as `--time-based` are passed to the scheduler. Failures return a nonzero exit status to Task Scheduler without waiting for keyboard input.

### Linux/Mac Cron Job

```bash
# Run every hour for time-based notifications
0 * * * * cd /path/to/subscription_manager_backend && python scheduler.py --time-based

# Or run daily at 3 PM for general notifications
0 15 * * * cd /path/to/subscription_manager_backend && python scheduler.py

# Or using Django management command with time filtering
0 9 * * * cd /path/to/subscription_manager_backend && python manage.py send_renewal_notifications --time 09:00
0 15 * * * cd /path/to/subscription_manager_backend && python manage.py send_renewal_notifications --time 15:00
0 21 * * * cd /path/to/subscription_manager_backend && python manage.py send_renewal_notifications --time 21:00
```

## ⏰ How Time-Based Notifications Work

### User Experience:
1. **User creates subscription**: "Netflix Premium" ending on Jan 30th at 9:00 AM
2. **System schedules notification**: Jan 27th at 9:00 AM (3 days before)
3. The user receives the reminder on the first successful hourly run after that local time, while the renewal is still upcoming.

### Technical Implementation:
- **Renewal Time Field**: Optional time field in subscription form (defaults to 3:00 PM)
- The hourly job checks each upcoming event against its local reminder time, including across midnight and daylight-saving changes. Catch-up ends when the event time passes. Each team member has their own delivery record. Existing subscription-wide delivery records suppress repeats after upgrading.
- The `--time` parameter simulates a scheduler run at that server time. Daily mode uses the recipient’s local calendar day for eligibility and skips events whose time has passed.
- **Fallback**: Subscriptions without specific time use default (3:00 PM)

### Example Scenarios:
```bash
# Netflix ends at 9:00 AM → Notification at 9:00 AM, 3 days before
python manage.py send_renewal_notifications --time 09:00

# Spotify ends at 3:30 PM → Notification at 3:30 PM, 3 days before  
python manage.py send_renewal_notifications --time 15:30

# GitHub (no time set) → Notification at 3:00 PM, 3 days before
python manage.py send_renewal_notifications --time 15:00
```

## 📧 Email Templates

The system uses three email templates:

1. **Subject**: `templates/emails/renewal_reminder_subject.txt`
2. **Text Version**: `templates/emails/renewal_reminder.txt`
3. **HTML Version**: `templates/emails/renewal_reminder.html`

### Email Content Includes:
- Service name and icon
- Renewal date AND time (if specified)
- Cost and billing cycle
- Direct link to manage subscription

## 🔍 Testing

### Create Test Subscription with Time

1. Go to "Add Subscription" in your DUES dashboard
2. Fill in service details
3. **Set Renewal Time**: Choose specific time (e.g., 9:00 AM)
4. Save subscription

### Test Time-Based Notifications

```bash
# Test specific time
python manage.py send_renewal_notifications --time 09:00 --dry-run

# Test current time
python scheduler.py --time-based

# Test all subscriptions
python manage.py send_renewal_notifications --dry-run
```

## 📊 Monitoring

### Check Notification Logs

```python
from subscriptions.models import NotificationLog

# View recent notifications
recent_notifications = NotificationLog.objects.all()[:10]
for notif in recent_notifications:
    print(f"{notif.subscription.service_name} - {notif.sent_at}")
```

### Log Files

- `renewal_notifications.log` - Contains detailed execution logs with time filtering info

## 🛠️ Troubleshooting

### Common Issues

1. **Wrong notification time**
   - Check subscription's `renewal_time` field
   - Verify scheduler is running at correct intervals
   - Use `--time` parameter to target specific times

2. **Missing notifications**
   - Ensure renewal_time is set on subscriptions
   - Check if time-based filtering is too restrictive
   - Verify cron job/task scheduler timing

3. **Too many notifications**
   - System prevents duplicates automatically
   - Check `NotificationLog` for sent notifications
   - Use dry-run mode to test before sending

### Debug Commands

```bash
# Check what would be sent at specific time
python manage.py send_renewal_notifications --time 15:30 --dry-run

# Check all subscriptions due
python manage.py send_renewal_notifications --dry-run

# Test time-based filtering
python scheduler.py --time-based
```

## 🔐 Security Considerations

1. **Email Credentials**: Store email passwords securely in environment variables
2. **Rate Limiting**: The system sends emails in batches to avoid spam filters
3. **Delivery recovery**: An interrupted worker’s unconfirmed email reservation expires. A later run can retry while the event is still upcoming.
4. **Data Privacy**: Only necessary subscription data is included in emails

## 📈 Future Enhancements

Potential improvements you could add:

3. **Smart Scheduling**: Learn from user behavior to optimize notification times
4. **Snooze Feature**: Allow users to delay notifications

---

Run the time-based job hourly. It also rechecks configured spending caps. Billing also recovers missed charges from each active subscription’s stored next renewal through the run date. Repeating the job preserves one charge per scheduled date.
