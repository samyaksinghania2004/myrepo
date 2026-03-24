from __future__ import annotations

from datetime import timedelta
from random import SystemRandom
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import (
    EmailOTPRequestForm,
    EmailOTPVerifyForm,
    EmailOrUsernameAuthenticationForm,
    ResendVerificationForm,
    SignUpForm,
)
from .models import EmailOTPChallenge
from .utils import (
    env_int,
    send_signup_verification_email,
    read_signed_user_token,
)

User = get_user_model()


def _client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _generate_otp_code():
    return f"{SystemRandom().randrange(0, 1000000):06d}"


def _send_login_otp_email(user, code, request):
    expiry_seconds = env_int("CLUBSHUB_OTP_EXPIRY_SECONDS", 300)
    expiry_minutes = max(expiry_seconds // 60, 1)
    verify_url = request.build_absolute_uri(reverse("accounts:otp_verify"))

    send_mail(
        subject="Your ClubsHub login code",
        message=(
            f"Hello {user.display_name},\n\n"
            f"Your one-time ClubsHub login code is: {code}\n\n"
            f"This code expires in {expiry_minutes} minute(s) and can only be used once.\n"
            f"You can enter it here: {verify_url}\n\n"
            "If you did not request this code, you can safely ignore this email.\n\n"
            "Regards,\n"
            "ClubsHub"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )


def signup_view(request):
    if request.user.is_authenticated:
        return redirect("clubs_events:event_feed")

    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            send_signup_verification_email(user, request)
            params = urlencode({"email": user.email})
            return redirect(f"{reverse('accounts:signup_pending')}?{params}")
    else:
        form = SignUpForm()

    return render(request, "accounts/signup.html", {"form": form})


def signup_pending_view(request):
    if request.user.is_authenticated:
        return redirect("clubs_events:event_feed")

    return render(
        request,
        "accounts/signup_pending.html",
        {"email": request.GET.get("email", "")},
    )


def verify_email_view(request, token):
    max_age = env_int("CLUBSHUB_EMAIL_VERIFICATION_MAX_AGE_SECONDS", 86400)
    success = False
    already_verified = False
    message = "This verification link is invalid or has expired."

    try:
        payload = read_signed_user_token(token, "verify-email", max_age=max_age)
        user = User.objects.filter(
            pk=payload["user_id"],
            email__iexact=payload["email"],
        ).first()

        if user is None:
            message = "This verification link is invalid or has expired."
        elif user.signup_reported_at or not user.is_active:
            message = "This signup has already been reported and deactivated."
        elif user.email_verified:
            success = True
            already_verified = True
            message = "Your email address is already verified. You can log in."
        else:
            user.email_verified = True
            user.email_verified_at = timezone.now()
            user.is_active = True
            user.save(update_fields=["email_verified", "email_verified_at", "is_active"])
            success = True
            message = "Your email has been verified successfully. You can now log in."
    except Exception:
        message = "This verification link is invalid or has expired."

    return render(
        request,
        "accounts/email_verification_result.html",
        {
            "success": success,
            "already_verified": already_verified,
            "message": message,
        },
    )


def report_signup_view(request, token):
    max_age = env_int("CLUBSHUB_SIGNUP_REPORT_MAX_AGE_SECONDS", 86400)
    success = False
    message = "This reporting link is invalid or has expired."

    try:
        payload = read_signed_user_token(token, "report-signup", max_age=max_age)
        user = User.objects.filter(
            pk=payload["user_id"],
            email__iexact=payload["email"],
        ).first()

        if user is None:
            message = "This reporting link is invalid or has expired."
        elif user.signup_reported_at:
            success = True
            message = "This signup has already been reported and deactivated."
        else:
            user.signup_reported_at = timezone.now()
            user.is_active = False
            user.email_verified = False
            user.save(update_fields=["signup_reported_at", "is_active", "email_verified"])
            success = True
            message = "The signup has been reported and the account has been deactivated."
    except Exception:
        message = "This reporting link is invalid or has expired."

    return render(
        request,
        "accounts/signup_report_result.html",
        {
            "success": success,
            "message": message,
        },
    )


def resend_verification_view(request):
    if request.user.is_authenticated:
        return redirect("clubs_events:event_feed")

    if request.method == "POST":
        form = ResendVerificationForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            user = User.objects.filter(
                email__iexact=email,
                is_active=True,
                email_verified=False,
                signup_reported_at__isnull=True,
            ).first()
            if user:
                send_signup_verification_email(user, request)

            messages.success(
                request,
                "If an eligible account exists, we have sent a fresh verification email.",
            )
            return redirect("accounts:login")
    else:
        form = ResendVerificationForm(initial={"email": request.GET.get("email", "")})

    return render(request, "accounts/resend_verification.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("clubs_events:event_feed")

    next_url = request.GET.get("next") or request.POST.get("next") or ""

    if request.method == "POST":
        form = EmailOrUsernameAuthenticationForm(request, request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, f"Welcome back, {user.display_name}!")
            return redirect(next_url or "clubs_events:event_feed")
    else:
        form = EmailOrUsernameAuthenticationForm(request)

    otp_request_form = EmailOTPRequestForm(
        initial={"email": request.GET.get("email", "")}
    )

    return render(
        request,
        "accounts/login.html",
        {
            "form": form,
            "otp_request_form": otp_request_form,
            "next": next_url,
        },
    )


def request_login_otp_view(request):
    if request.user.is_authenticated:
        return redirect("clubs_events:event_feed")

    if request.method != "POST":
        return redirect("accounts:login")

    next_url = request.POST.get("next") or ""
    form = EmailOTPRequestForm(request.POST)

    if form.is_valid():
        email = form.cleaned_data["email"]
        user = User.objects.filter(
            email__iexact=email,
            is_active=True,
            email_verified=True,
        ).first()

        if user:
            latest = (
                EmailOTPChallenge.objects.filter(
                    user=user,
                    purpose=EmailOTPChallenge.Purpose.LOGIN,
                )
                .order_by("-created_at")
                .first()
            )

            now = timezone.now()
            cooldown_seconds = env_int("CLUBSHUB_OTP_RESEND_COOLDOWN_SECONDS", 60)
            otp_expiry_seconds = env_int("CLUBSHUB_OTP_EXPIRY_SECONDS", 300)

            can_send = True
            if (
                latest
                and latest.last_sent_at
                and latest.is_usable()
                and (now - latest.last_sent_at).total_seconds() < cooldown_seconds
            ):
                can_send = False

            if can_send:
                EmailOTPChallenge.objects.filter(
                    user=user,
                    purpose=EmailOTPChallenge.Purpose.LOGIN,
                    consumed_at__isnull=True,
                ).update(consumed_at=now)

                code = _generate_otp_code()
                challenge = EmailOTPChallenge(
                    user=user,
                    email=user.email,
                    purpose=EmailOTPChallenge.Purpose.LOGIN,
                    expires_at=now + timedelta(seconds=otp_expiry_seconds),
                    last_sent_at=now,
                    request_ip=_client_ip(request),
                    user_agent=(request.META.get("HTTP_USER_AGENT", "") or "")[:255],
                )
                challenge.set_code(code)
                challenge.save()
                _send_login_otp_email(user, code, request)

        messages.success(
            request,
            "If an eligible account exists, we have sent a one-time code to the registered email address.",
        )
        params = {"email": form.cleaned_data["email"]}
        if next_url:
            params["next"] = next_url
        return redirect(f"{reverse('accounts:otp_verify')}?{urlencode(params)}")

    password_form = EmailOrUsernameAuthenticationForm(request)
    return render(
        request,
        "accounts/login.html",
        {
            "form": password_form,
            "otp_request_form": form,
            "next": next_url,
        },
    )


def otp_verify_view(request):
    if request.user.is_authenticated:
        return redirect("clubs_events:event_feed")

    next_url = request.GET.get("next") or request.POST.get("next") or ""
    initial_email = request.GET.get("email") or request.POST.get("email") or ""

    if request.method == "POST":
        form = EmailOTPVerifyForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            code = form.cleaned_data["code"]

            user = User.objects.filter(
                email__iexact=email,
                is_active=True,
                email_verified=True,
            ).first()
            challenge = None
            if user:
                challenge = (
                    EmailOTPChallenge.objects.filter(
                        user=user,
                        purpose=EmailOTPChallenge.Purpose.LOGIN,
                        consumed_at__isnull=True,
                    )
                    .order_by("-created_at")
                    .first()
                )

            max_attempts = env_int("CLUBSHUB_OTP_MAX_ATTEMPTS", 5)

            if not user or not challenge:
                messages.error(request, "Invalid or expired code. Please request a new one.")
            elif challenge.is_expired:
                challenge.mark_consumed()
                messages.error(request, "Invalid or expired code. Please request a new one.")
            elif challenge.failed_attempts >= max_attempts:
                if not challenge.is_consumed:
                    challenge.mark_consumed()
                messages.error(
                    request,
                    "Too many failed attempts. Please request a new code.",
                )
            elif challenge.check_code(code):
                challenge.mark_consumed()
                login(request, user, backend="accounts.backends.EmailOrUsernameModelBackend")
                messages.success(request, f"Welcome back, {user.display_name}!")
                return redirect(next_url or "clubs_events:event_feed")
            else:
                challenge.failed_attempts += 1
                update_fields = ["failed_attempts"]
                if challenge.failed_attempts >= max_attempts:
                    challenge.consumed_at = timezone.now()
                    update_fields.append("consumed_at")
                challenge.save(update_fields=update_fields)

                if challenge.failed_attempts >= max_attempts:
                    messages.error(
                        request,
                        "Too many failed attempts. Please request a new code.",
                    )
                else:
                    messages.error(request, "Invalid code. Please try again.")
    else:
        form = EmailOTPVerifyForm(initial={"email": initial_email})

    return render(
        request,
        "accounts/otp_verify.html",
        {
            "form": form,
            "otp_request_form": EmailOTPRequestForm(initial={"email": initial_email}),
            "next": next_url,
        },
    )


@login_required
def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect("accounts:login")


@login_required
def profile_view(request):
    memberships = request.user.club_memberships.select_related("club").all()
    my_rooms = request.user.room_handles.select_related("room").all()
    my_events = request.user.registrations.select_related("event", "event__club").all()

    context = {
        "memberships": memberships,
        "my_rooms": my_rooms,
        "my_events": my_events,
    }
    return render(request, "accounts/profile.html", context)
