from __future__ import annotations

import os

from django.conf import settings
from django.core import signing
from django.core.mail import send_mail
from django.urls import reverse


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def env_str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def build_absolute_uri(request, path: str) -> str:
    if request is not None:
        return request.build_absolute_uri(path)

    base_url = env_str("CLUBSHUB_BASE_URL", "").rstrip("/")
    if base_url:
        return f"{base_url}{path}"
    return path


def _signing_salt(purpose: str) -> str:
    return f"clubshub.accounts.{purpose}"


def make_signed_user_token(user, purpose: str) -> str:
    payload = {
        "user_id": user.pk,
        "email": user.email,
    }
    return signing.dumps(payload, salt=_signing_salt(purpose))


def read_signed_user_token(token: str, purpose: str, max_age: int):
    return signing.loads(token, salt=_signing_salt(purpose), max_age=max_age)


def send_signup_verification_email(user, request) -> None:
    verify_token = make_signed_user_token(user, "verify-email")
    report_token = make_signed_user_token(user, "report-signup")

    verify_url = build_absolute_uri(
        request,
        reverse("accounts:verify_email", kwargs={"token": verify_token}),
    )
    report_url = build_absolute_uri(
        request,
        reverse("accounts:report_signup", kwargs={"token": report_token}),
    )

    site_name = env_str("CLUBSHUB_SITE_NAME", "ClubsHub")

    send_mail(
        subject=f"Verify your {site_name} account",
        message=(
            f"Hello {user.display_name},\n\n"
            f"A ClubsHub account was registered using this email address.\n\n"
            f"Verify your account: {verify_url}\n\n"
            f"If this was not you, report and deactivate this signup: {report_url}\n\n"
            "If you did not request this account, please use the second link above.\n\n"
            f"Regards,\n{site_name}"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )
