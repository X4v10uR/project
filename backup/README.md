# Subly - Subscription Management SaaS

A premium Subscription Management SaaS application built with Django and Tailwind CSS.

## Features
- **Authentication**: Secure email-based login and signup.
- **Subscription Tracker**: Add, edit, and delete your recurring services.
- **Dashboard**: Visualize your monthly/yearly spend and upcoming renewals.
- **Responsive Design**: Premium look and feel, optimized for all devices.

## Tech Stack
- **Backend**: Django (Python)
- **Frontend**: Django Templates + Tailwind CSS (via CDN)
- **Database**: SQLite (default)

## Setup Instructions

1. **Install Dependencies**
   ```bash
   pip install django django-environ djangorestframework django-cors-headers python-dateutil
   ```

2. **Run Migrations**
   ```bash
   python manage.py migrate
   ```

3. **Seed Demo Data** (Optional but recommended)
   ```bash
   python seed_demo.py
   ```
   *Creates a demo user: `demo@subly.com` with password `demo1234` and sample subscriptions.*

4. **Start the Server**
   ```bash
   python manage.py runserver
   ```

5. **Access the App**
   Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.

## Credentials for Demo
- **Email**: `demo@subly.com`
- **Password**: `demo1234`
