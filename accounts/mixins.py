from __future__ import annotations

from functools import wraps

from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib.auth.views import redirect_to_login
from django.http import HttpRequest, HttpResponseForbidden


def user_has_role(user, *roles: str) -> bool:
    return bool(user.is_authenticated and user.role in roles)


def role_required(*roles: str):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request: HttpRequest, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if request.user.role not in roles:
                return HttpResponseForbidden("You do not have permission to access this page.")
            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator


class RoleRequiredMixin(UserPassesTestMixin):
    allowed_roles: tuple[str, ...] = ()
    permission_denied_message = "You do not have permission to access this page."

    def test_func(self):
        return user_has_role(self.request.user, *self.allowed_roles)
