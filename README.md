# ClubsHub Website

A Django-based implementation of the ClubsHub course project.

## What is implemented

- IITK-only sign-up and login with role-aware navigation.
- Club creation, editing, following and follower visibility for managers.
- Event creation, editing, cancellation, registration, waitlist promotion and attendance marking.
- Personalised event feed and basic analytics dashboard.
- Discussion rooms with anonymous handles, public/restricted access, message posting, reporting and moderation.
- Notifications and audit logs.
- Demo data seeding for quick evaluation.

## Project structure

- `accounts/` – custom user model, login/signup, profile, role helpers.
- `clubs_events/` – clubs, events, registrations, attendance and analytics.
- `rooms/` – discussion rooms, anonymous handles, messages, reports and moderation.
- `core/` – notifications, audit logs, search, help page and demo seed command.
- `config/` – Django settings and URL routing.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Open the app at `http://127.0.0.1:8000/`.

## Demo users

All demo users use the password `Password@123`.

- `student1`
- `coordinator1`
- `admin1`

## Deployment notes for your IITK server

1. Copy the project to the server.
2. Set `CLUBSHUB_ALLOWED_HOSTS` to include `csehn6.cse.iitk.ac.in` and `172.27.16.252`.
3. Run migrations and create a superuser or seed demo data.
4. Start with Django's dev server for testing, then switch to Gunicorn + Nginx for production.

## Suggested next steps

- Replace email/password auth with IITK SSO or email-OTP.
- Add richer attendance and club analytics.
- Add real-time chat using Django Channels or polling APIs.
- Expose a REST API for the mobile app.

## Permissions overhaul (2026)
See `PERMISSIONS.md` for the complete matrix and migration notes.
