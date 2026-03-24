from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone


class Notification(models.Model):
    class Type(models.TextChoices):
        EVENT_REGISTERED = "event_registered", "Event registered"
        WAITLISTED = "waitlisted", "Waitlisted"
        WAITLIST_PROMOTED = "waitlist_promoted", "Waitlist promoted"
        EVENT_UPDATED = "event_updated", "Event updated"
        EVENT_CANCELLED = "event_cancelled", "Event cancelled"
        MODERATION_ACTION = "moderation_action", "Moderation action"
        ANNOUNCEMENT = "announcement", "Announcement"
        INVITE = "invite", "Invite"
        GENERIC = "generic", "Generic"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="notifications"
    )
    text = models.CharField(max_length=255)
    notification_type = models.CharField(
        max_length=32, choices=Type.choices, default=Type.GENERIC
    )
    is_read = models.BooleanField(default=False)
    event = models.ForeignKey(
        "clubs_events.Event",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
    )
    room = models.ForeignKey(
        "rooms.DiscussionRoom",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
    )
    message = models.ForeignKey(
        "rooms.Message",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]


class AuditLogEntry(models.Model):
    class ActionType(models.TextChoices):
        CLUB_CREATED = "club_created", "Club created"
        CLUB_UPDATED = "club_updated", "Club updated"
        CLUB_JOINED = "club_joined", "Club joined"
        CLUB_LEFT = "club_left", "Club left"
        CLUB_MEMBER_REMOVED = "club_member_removed", "Club member removed"
        ROLE_GRANTED = "role_granted", "Role granted"
        ROLE_REVOKED = "role_revoked", "Role revoked"
        EVENT_CREATED = "event_created", "Event created"
        EVENT_UPDATED = "event_updated", "Event updated"
        EVENT_CANCELLED = "event_cancelled", "Event cancelled"
        EVENT_ARCHIVED = "event_archived", "Event archived"
        ROOM_CREATED = "room_created", "Room created"
        ROOM_UPDATED = "room_updated", "Room updated"
        ROOM_ARCHIVED = "room_archived", "Room archived"
        ROOM_INVITE_CREATED = "room_invite_created", "Room invite created"
        ROOM_INVITE_UPDATED = "room_invite_updated", "Room invite updated"
        ANNOUNCEMENT_CREATED = "announcement_created", "Announcement created"
        REPORT_DISMISSED = "report_dismissed", "Report dismissed"
        MESSAGE_DELETED = "message_deleted", "Message deleted"
        HANDLE_MUTED = "handle_muted", "Handle muted"
        HANDLE_EXPELLED = "handle_expelled", "Handle expelled"
        HANDLE_REVEALED = "handle_revealed", "Handle revealed"
        DELETE_AND_MUTE = "delete_and_mute", "Delete and mute"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    action_type = models.CharField(max_length=32, choices=ActionType.choices)
    acting_user = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_actions",
    )
    target_user = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_targets",
    )
    target_handle_name = models.CharField(max_length=64, blank=True)
    room = models.ForeignKey(
        "rooms.DiscussionRoom",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    event = models.ForeignKey(
        "clubs_events.Event",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    message = models.ForeignKey(
        "rooms.Message",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    reason = models.CharField(max_length=255, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
