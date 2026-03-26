from __future__ import annotations

from datetime import timedelta

from django.utils import timezone


class LastSeenMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            now = timezone.now()
            last_seen = user.last_seen_at
            if last_seen is None or now - last_seen >= timedelta(minutes=1):
                user.last_seen_at = now
                user.save(update_fields=["last_seen_at"])
        return response
