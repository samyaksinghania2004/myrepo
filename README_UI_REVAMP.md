This bundle contains a first-pass UI + interaction revamp for ClubsHub based on the latest public GitHub repo.

Included fixes:
- Major layout refresh (new base template, CSS, JS)
- Coordinator/secretary create-event and create-room entry points surfaced in the UI
- Rich notifications with title, body and click-through links
- Browser notification polling (works best over HTTPS; desktop browser notifications require HTTPS or localhost)
- Self-report blocking
- Leave-room action
- Report review page with direct jump back into room context and highlighted message support
- Admin event creation bug fix in Event.clean()
- Delete button for own messages no longer depends on the edit window
- Edit button now only appears while a message is actually editable
- Room announcements shown directly in room view

Apply on server:
1. Overlay these files onto the repo.
2. Activate the virtualenv.
3. Run:
   python manage.py migrate
   python manage.py collectstatic --noinput
   python manage.py runserver 0.0.0.0:8000

Notes:
- The notification model changed, so the included core migration must be applied.
- Desktop browser notifications will only show as true OS/browser notifications on HTTPS or localhost. On plain HTTP, the frontend falls back to in-page toast alerts.
- This bundle focuses on the main interaction surfaces first. You can request a second bundle later for deeper template coverage or a more React-like frontend migration path.
