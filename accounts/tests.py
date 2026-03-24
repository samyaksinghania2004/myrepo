from __future__ import annotations

from django.contrib.auth import authenticate, get_user_model
from django.core import mail, signing
from django.test import TestCase, override_settings
from django.urls import reverse

from .forms import SignUpForm
from .models import EmailOTPChallenge

User = get_user_model()


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class AccountsTests(TestCase):
    def test_signup_requires_iitk_email(self):
        form = SignUpForm(
            data={
                "username": "alice",
                "first_name": "Alice",
                "last_name": "Test",
                "email": "alice@gmail.com",
                "password1": "StrongPass@123",
                "password2": "StrongPass@123",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_email_or_username_backend_authenticates_email(self):
        user = User.objects.create_user(
            username="alice",
            email="alice@iitk.ac.in",
            password="StrongPass@123",
        )
        authenticated = authenticate(username="alice@iitk.ac.in", password="StrongPass@123")
        self.assertEqual(authenticated, user)

    def test_signup_creates_unverified_user_and_sends_email(self):
        response = self.client.post(
            reverse("accounts:signup"),
            data={
                "username": "newuser",
                "first_name": "New",
                "last_name": "User",
                "email": "newuser@iitk.ac.in",
                "password1": "StrongPass@123",
                "password2": "StrongPass@123",
            },
        )
        self.assertRedirects(
            response,
            reverse("accounts:signup_pending") + "?email=newuser%40iitk.ac.in",
            fetch_redirect_response=False,
        )
        user = User.objects.get(username="newuser")
        self.assertFalse(user.email_verified)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Verify your ClubsHub account", mail.outbox[0].subject)

    def test_verify_email_link_marks_user_verified(self):
        user = User.objects.create_user(
            username="verifyme",
            email="verifyme@iitk.ac.in",
            password="StrongPass@123",
            email_verified=False,
        )
        token = signing.dumps(
            {"user_id": user.pk, "email": user.email},
            salt="clubshub.accounts.verify-email",
        )

        response = self.client.get(reverse("accounts:verify_email", args=[token]))
        self.assertEqual(response.status_code, 200)

        user.refresh_from_db()
        self.assertTrue(user.email_verified)
        self.assertIsNotNone(user.email_verified_at)

    def test_report_signup_link_deactivates_user(self):
        user = User.objects.create_user(
            username="reportme",
            email="reportme@iitk.ac.in",
            password="StrongPass@123",
            email_verified=False,
        )
        token = signing.dumps(
            {"user_id": user.pk, "email": user.email},
            salt="clubshub.accounts.report-signup",
        )

        response = self.client.get(reverse("accounts:report_signup", args=[token]))
        self.assertEqual(response.status_code, 200)

        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertFalse(user.email_verified)
        self.assertIsNotNone(user.signup_reported_at)

    def test_unverified_user_cannot_password_login(self):
        user = User.objects.create_user(
            username="pendinguser",
            email="pendinguser@iitk.ac.in",
            password="StrongPass@123",
            email_verified=False,
        )

        response = self.client.post(
            reverse("accounts:login"),
            data={
                "identifier": user.email,
                "password": "StrongPass@123",
            },
        )
        self.assertContains(response, "Please verify your email address before logging in.")

    def test_verified_user_can_request_otp(self):
        user = User.objects.create_user(
            username="otpuser",
            email="otpuser@iitk.ac.in",
            password="StrongPass@123",
            email_verified=True,
        )

        response = self.client.post(
            reverse("accounts:request_login_otp"),
            data={"email": user.email},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(EmailOTPChallenge.objects.filter(user=user).count(), 1)
        challenge = EmailOTPChallenge.objects.get(user=user)
        self.assertNotEqual(challenge.code_hash, "")
        self.assertEqual(len(mail.outbox), 1)
