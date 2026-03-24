from __future__ import annotations

from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    class Role(models.TextChoices):
        STUDENT = "student", "Student"
        CLUB_REP = "club_rep", "Club Representative"
        MODERATOR = "moderator", "Moderator"
        INSTITUTE_ADMIN = "institute_admin", "Institute Admin"
        SYSTEM_ADMIN = "system_admin", "System Admin"

    email = models.EmailField(unique=True)
    role = models.CharField(max_length=32, choices=Role.choices, default=Role.STUDENT)
    is_globally_banned = models.BooleanField(
        default=False,
        help_text="Prevents the user from joining rooms and registering for events.",
    )
    email_verified = models.BooleanField(
        default=True,
        help_text="Existing users remain verified; new signups start unverified.",
    )
    email_verified_at = models.DateTimeField(blank=True, null=True)
    signup_reported_at = models.DateTimeField(blank=True, null=True)

    def clean(self) -> None:
        super().clean()
        if self.email and not self.email.lower().endswith("@iitk.ac.in"):
            raise ValidationError({"email": "Only IITK email addresses are allowed."})

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.lower()
        return super().save(*args, **kwargs)

    @property
    def display_name(self) -> str:
        full_name = self.get_full_name().strip()
        return full_name or self.username

    def __str__(self) -> str:
        return f"{self.display_name} ({self.get_role_display()})"


class EmailOTPChallenge(models.Model):
    class Purpose(models.TextChoices):
        LOGIN = "login", "Login"

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="email_otp_challenges",
    )
    email = models.EmailField(db_index=True)
    purpose = models.CharField(
        max_length=32,
        choices=Purpose.choices,
        default=Purpose.LOGIN,
    )
    code_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(blank=True, null=True)
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    last_sent_at = models.DateTimeField(default=timezone.now)
    request_ip = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["email", "purpose", "created_at"]),
        ]

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.lower()
        return super().save(*args, **kwargs)

    def set_code(self, code: str) -> None:
        self.code_hash = make_password(code)

    def check_code(self, code: str) -> bool:
        return check_password(code, self.code_hash)

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_consumed(self) -> bool:
        return self.consumed_at is not None

    def is_usable(self) -> bool:
        return not self.is_consumed and not self.is_expired

    def mark_consumed(self) -> None:
        self.consumed_at = timezone.now()
        self.save(update_fields=["consumed_at"])

    def __str__(self) -> str:
        return f"{self.email} / {self.purpose} / {self.created_at:%Y-%m-%d %H:%M:%S}"
