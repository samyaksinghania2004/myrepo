# ClubsHub Website Feature Map

This file maps the current implementation to the requirements in the SRS.

## Implemented end-to-end

- F1–F4: IITK-only account creation, authentication, roles, permission checks.
- F5–F9: Club creation/editing, representative assignment, browsing, follow/unfollow, follower visibility for managers.
- F10–F18: Event creation/editing/cancellation, feed filters, registration, cancellation, waitlist promotion.
- F19–F20: Keyword search across clubs, events and rooms with input length limits.
- F21–F28: Room creation, public/restricted access, anonymous handles, message posting, edit/delete window, message reporting.
- F29–F38: Moderation dashboard, delete/mute/expel/reveal actions, audit logging, notifications view.
- F39: Basic analytics and attendance percentages.

## Intentionally simplified for the first website iteration

- Authentication uses IITK email + password instead of OTP/SSO.
- Notifications are in-app and use Django's console email backend by default.
- Discussion rooms use standard page refresh instead of real-time WebSockets.
- Restricted room access is handled by pending requests + manual approval.

## Good next milestones

1. Replace password auth with IITK SSO or email-OTP.
2. Add REST API endpoints for the mobile app.
3. Add richer moderator policy controls and global bans UI.
4. Add background jobs / asynchronous notification delivery.
5. Add production deployment with Gunicorn, Nginx and PostgreSQL.
