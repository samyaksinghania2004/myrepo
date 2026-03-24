from django.contrib import admin

from .models import AuditLogEntry, Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "notification_type", "text", "is_read", "created_at")
    list_filter = ("notification_type", "is_read", "created_at")
    search_fields = ("text", "user__username", "user__email")


@admin.register(AuditLogEntry)
class AuditLogEntryAdmin(admin.ModelAdmin):
    list_display = (
        "action_type",
        "acting_user",
        "target_user",
        "target_handle_name",
        "created_at",
    )
    list_filter = ("action_type", "created_at")
    search_fields = (
        "reason",
        "target_handle_name",
        "acting_user__username",
        "target_user__username",
    )
