from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import EmailOTPChallenge, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (
        (
            "ClubsHub",
            {
                "fields": (
                    "role",
                    "is_globally_banned",
                    "email_verified",
                    "email_verified_at",
                    "signup_reported_at",
                ),
            },
        ),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        (
            "ClubsHub",
            {
                "fields": (
                    "email",
                    "role",
                    "is_globally_banned",
                    "email_verified",
                ),
            },
        ),
    )
    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "role",
        "email_verified",
        "is_staff",
        "is_globally_banned",
    )
    list_filter = (
        "role",
        "email_verified",
        "is_staff",
        "is_superuser",
        "is_globally_banned",
    )
    search_fields = ("username", "email", "first_name", "last_name")


@admin.register(EmailOTPChallenge)
class EmailOTPChallengeAdmin(admin.ModelAdmin):
    list_display = (
        "email",
        "purpose",
        "user",
        "created_at",
        "expires_at",
        "consumed_at",
        "failed_attempts",
    )
    list_filter = ("purpose", "created_at", "expires_at", "consumed_at")
    search_fields = ("email", "user__username", "user__email")
    readonly_fields = (
        "user",
        "email",
        "purpose",
        "code_hash",
        "created_at",
        "last_sent_at",
        "request_ip",
        "user_agent",
    )
