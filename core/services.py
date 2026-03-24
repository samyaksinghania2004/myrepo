from __future__ import annotations

from core.models import AuditLogEntry, Notification


def create_notification(
    *,
    user,
    text: str,
    notification_type: str = Notification.Type.GENERIC,
    event=None,
    room=None,
    message=None,
):
    return Notification.objects.create(
        user=user,
        text=text,
        notification_type=notification_type,
        event=event,
        room=room,
        message=message,
    )


def log_audit(
    *,
    action_type: str,
    acting_user=None,
    target_user=None,
    target_handle_name: str = "",
    room=None,
    event=None,
    message=None,
    reason: str = "",
    details: dict | None = None,
):
    return AuditLogEntry.objects.create(
        action_type=action_type,
        acting_user=acting_user,
        target_user=target_user,
        target_handle_name=target_handle_name,
        room=room,
        event=event,
        message=message,
        reason=reason,
        details=details or {},
    )
