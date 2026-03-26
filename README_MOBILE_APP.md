# ClubsHub Mobile App Guide

ClubsHub now works as an installable mobile app using a Progressive Web App setup.

## What was added

- Web app manifest
- Service worker
- Offline fallback page
- App icons
- Install button for supported browsers

## Why this approach

- It reuses the same Django project and mobile website.
- It is much faster and safer than rewriting the frontend in a native framework.
- It avoids heavy caching, so the app does not make the website feel stale or hang.

## Run the project

```bash
cd myrepo
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Open the site at the URL printed by Django.

## Install as an app on Android

1. Open the site in Chrome.
2. Log in.
3. Tap the `Install app` button if it appears.
4. If the button does not appear, use the browser menu and choose `Add to Home screen` or `Install app`.

## Important note for professor demo

For a proper install prompt on a real phone, the site should be served on:

- `https://...`
- or `http://localhost` on the same device

If you are using a remote server, open the real server URL on the phone. Do not use `127.0.0.1` unless the site is running on that same phone.

## What to say in the demo

- "This is the same ClubsHub system, now packaged as an installable mobile app using PWA."
- "It uses the same backend and works both as a website and as an app."
- "The caching strategy is intentionally lightweight so fresh campus data still loads normally."
