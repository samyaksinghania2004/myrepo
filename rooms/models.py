from __future__ import annotations

import uuid
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class DiscussionRoom(models.Model):
    class RoomType(models.TextChoices):
        CLUB = "club", "Club"
        EVENT = "event", "Event"
        TOPIC = "topic", "Topic"

    class AccessType(models.TextChoices):
        PUBLIC = "public", "Public"
        RESTRICTED = "restricted", "Restricted"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=60)
    description = models.TextField(max_length=400, blank=True)
    room_type = models.CharField(max_length=10, choices=RoomType.choices)
    access_type = models.CharField(max_length=15, choices=AccessType.choices)
    club = models.ForeignKey(
        "clubs_events.Club",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="discussion_rooms",
    )
    event = models.ForeignKey(
        "clubs_events.Event",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="discussion_rooms",
    )
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_rooms",
    )
    moderators = models.ManyToManyField(
        "accounts.User", related_name="moderated_rooms", blank=True
    )
    is_archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        super().clean()
        if self.room_type == self.RoomType.CLUB and not self.club:
            raise ValidationError("Club rooms must be associated with a club.")
        if self.room_type == self.RoomType.EVENT and not self.event:
            raise ValidationError("Event rooms must be associated with an event.")
        if self.room_type == self.RoomType.TOPIC and (self.club or self.event):
            raise ValidationError("Topic rooms should not be linked to a club or event.")

    def can_be_managed_by(self, user) -> bool:
        if not user.is_authenticated:
            return False
        if user.role in {user.Role.MODERATOR, user.Role.INSTITUTE_ADMIN, user.Role.SYSTEM_ADMIN}:
            return True
        if self.created_by_id == user.id:
            return True
        if self.club and self.club.can_be_managed_by(user):
            return True
        return self.moderators.filter(pk=user.pk).exists()


class RoomHandle(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        EXPELLED = "expelled", "Expelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(
        DiscussionRoom, on_delete=models.CASCADE, related_name="room_handles"
    )
    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="room_handles"
    )
    handle_name = models.CharField(max_length=24)
    status = models.CharField(max_length=16, choices=Status.choices)
    is_muted = models.BooleanField(default=False)
    revealed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    approved_at = models.DateTimeField(null=True, blank=True)
    expelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(fields=["room", "user"], name="unique_room_user"),
            models.UniqueConstraint(
                fields=["room", "handle_name"], name="unique_room_handle_name"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.handle_name} in {self.room.name}"

    @property
    def can_post(self) -> bool:
        return self.status == self.Status.APPROVED and not self.is_muted


class Message(models.Model):
    EDIT_WINDOW = timedelta(minutes=5)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(DiscussionRoom, on_delete=models.CASCADE, related_name="messages")
    handle = models.ForeignKey(RoomHandle, on_delete=models.CASCADE, related_name="messages")
    text = models.TextField(max_length=1000)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    is_edited = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deleted_messages",
    )

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.handle.handle_name}: {self.text[:40]}"

    def editable_until(self):
        return self.created_at + self.EDIT_WINDOW

    def can_be_edited_by(self, user) -> bool:
        return (
            not self.is_deleted
            and self.handle.user_id == user.id
            and timezone.now() <= self.editable_until()
        )

    def soft_delete(self, actor=None):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.deleted_by = actor
        self.save(update_fields=["is_deleted", "deleted_at", "deleted_by", "updated_at"])


class Report(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        DISMISSED = "dismissed", "Dismissed"
        ACTION_TAKEN = "action_taken", "Action taken"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="reports")
    reporter = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="reports_filed"
    )
    reason = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    resolved_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reports_resolved",
    )
    resolution_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Report on {self.message_id}"
