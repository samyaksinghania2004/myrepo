from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Count, Q
from django.utils import timezone

from core.permissions import LOCAL_ROLE_COORDINATOR, LOCAL_ROLE_MEMBER


class Club(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=80, unique=True)
    category = models.CharField(max_length=32)
    description = models.TextField(max_length=400)
    contact_email = models.EmailField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def can_be_managed_by(self, user) -> bool:
        from core.permissions import can_manage_club

        return can_manage_club(user, self)

    @property
    def follower_count(self) -> int:
        return self.memberships.filter(status=ClubMembership.Status.ACTIVE).count()


class ClubMembership(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        LEFT = "left", "Left"
        REMOVED = "removed", "Removed"

    class LocalRole(models.TextChoices):
        MEMBER = LOCAL_ROLE_MEMBER, "Member"
        SECRETARY = "secretary", "Club Secretary"
        COORDINATOR = LOCAL_ROLE_COORDINATOR, "Club Coordinator"

    club = models.ForeignKey(Club, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="club_memberships"
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    local_role = models.CharField(
        max_length=16, choices=LocalRole.choices, default=LocalRole.MEMBER
    )
    joined_at = models.DateTimeField(default=timezone.now)
    left_at = models.DateTimeField(null=True, blank=True)
    assigned_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_memberships",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["club", "user"], name="unique_club_membership")
        ]
        ordering = ["-joined_at"]

    def __str__(self) -> str:
        return f"{self.user.username} @ {self.club.name} ({self.local_role}/{self.status})"


class ClubFollow(models.Model):
    """Deprecated compatibility model kept for legacy data/history."""

    club = models.ForeignKey(Club, on_delete=models.CASCADE, related_name="club_follows")
    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="club_follows"
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["club", "user"], name="unique_club_follow")
        ]
        ordering = ["-created_at"]


class EventQuerySet(models.QuerySet):
    def upcoming(self):
        return self.filter(start_time__gte=timezone.now())

    def published(self):
        return self.filter(status=Event.Status.PUBLISHED)


class Event(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        CANCELLED = "cancelled", "Cancelled"
        COMPLETED = "completed", "Completed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    club = models.ForeignKey(Club, on_delete=models.CASCADE, related_name="events")
    title = models.CharField(max_length=120)
    description = models.TextField(max_length=800)
    venue = models.CharField(max_length=80)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    capacity = models.PositiveIntegerField(null=True, blank=True)
    tags = models.CharField(max_length=150, blank=True, help_text="Comma-separated tags.")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    waitlist_enabled = models.BooleanField(default=True)
    cancellation_reason = models.CharField(max_length=200, blank=True)
    is_archived = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_events",
    )
    updated_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_events",
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    objects = EventQuerySet.as_manager()

    class Meta:
        ordering = ["start_time", "title"]

    def __str__(self) -> str:
        return self.title

    def clean(self) -> None:
        super().clean()
        if self.end_time <= self.start_time:
            raise ValidationError("Event end time must be after the start time.")
        if self.capacity is not None and self.capacity <= 0:
            raise ValidationError("Capacity must be a positive number.")
        if self.status == self.Status.CANCELLED and not self.cancellation_reason:
            raise ValidationError("Please provide a cancellation reason.")

    def refresh_status_from_time(self, save: bool = True) -> None:
        if self.status == self.Status.PUBLISHED and timezone.now() >= self.end_time:
            self.status = self.Status.COMPLETED
            if save:
                self.save(update_fields=["status", "updated_at"])

    def can_be_managed_by(self, user) -> bool:
        from core.permissions import can_manage_event

        return can_manage_event(user, self)

    @property
    def registered_count(self) -> int:
        return self.registrations.filter(status=Registration.Status.REGISTERED).count()

    @property
    def waitlist_count(self) -> int:
        return self.registrations.filter(status=Registration.Status.WAITLISTED).count()

    @property
    def attendance_count(self) -> int:
        return self.registrations.filter(attendance=Registration.Attendance.PRESENT).count()

    @property
    def attendance_percentage(self) -> float:
        confirmed = self.registered_count
        if confirmed == 0:
            return 0.0
        return round((self.attendance_count / confirmed) * 100, 2)

    @property
    def is_open_for_registration(self) -> bool:
        return self.status == self.Status.PUBLISHED and timezone.now() < self.start_time

    def seats_remaining(self) -> int | None:
        if self.capacity is None:
            return None
        return max(self.capacity - self.registered_count, 0)

    def _status_message(self, status: str) -> str:
        if status == Registration.Status.REGISTERED:
            return f"You are registered for {self.title}."
        if status == Registration.Status.WAITLISTED:
            return f"You are on the waitlist for {self.title}."
        return f"Your registration for {self.title} has been updated."

    def register_user(self, user):
        from core.models import Notification
        from core.services import create_notification

        if user.is_globally_banned:
            raise ValidationError("This user is banned from event participation.")
        if not self.is_open_for_registration:
            raise ValidationError("This event is not open for registration.")

        with transaction.atomic():
            event = Event.objects.select_for_update().get(pk=self.pk)
            registration, _ = Registration.objects.select_for_update().get_or_create(
                user=user,
                event=event,
                defaults={"status": Registration.Status.CANCELLED},
            )
            if registration.status == Registration.Status.REGISTERED:
                return registration
            if event.capacity is None or event.registered_count < event.capacity:
                registration.status = Registration.Status.REGISTERED
                notification_type = Notification.Type.EVENT_REGISTERED
            else:
                if not event.waitlist_enabled:
                    raise ValidationError("This event is full and waitlisting is disabled.")
                registration.status = Registration.Status.WAITLISTED
                notification_type = Notification.Type.WAITLISTED
            registration.cancelled_at = None
            registration.save()
            create_notification(
                user=user,
                text=event._status_message(registration.status),
                notification_type=notification_type,
                event=event,
            )
            return registration

    def promote_waitlisted_user(self):
        from core.models import Notification
        from core.services import create_notification

        with transaction.atomic():
            next_in_line = (
                self.registrations.select_for_update()
                .filter(status=Registration.Status.WAITLISTED)
                .order_by("created_at")
                .first()
            )
            if not next_in_line:
                return None
            next_in_line.status = Registration.Status.REGISTERED
            next_in_line.save(update_fields=["status", "updated_at"])
            create_notification(
                user=next_in_line.user,
                text=f"You have been promoted from waitlist to registered for {self.title}.",
                notification_type=Notification.Type.WAITLIST_PROMOTED,
                event=self,
            )
            return next_in_line

    def cancel_registration_for_user(self, user):
        from core.services import create_notification

        with transaction.atomic():
            event = Event.objects.select_for_update().get(pk=self.pk)
            try:
                registration = Registration.objects.select_for_update().get(
                    event=event, user=user
                )
            except Registration.DoesNotExist as exc:
                raise ValidationError("You are not registered for this event.") from exc

            if timezone.now() >= event.start_time:
                raise ValidationError("Registrations cannot be changed after the event starts.")
            if registration.status == Registration.Status.CANCELLED:
                raise ValidationError("This registration is already cancelled.")

            previous_status = registration.status
            registration.status = Registration.Status.CANCELLED
            registration.cancelled_at = timezone.now()
            registration.save(update_fields=["status", "cancelled_at", "updated_at"])

            create_notification(
                user=user,
                text=f"Your registration for {event.title} has been cancelled.",
                event=event,
            )
            if previous_status == Registration.Status.REGISTERED:
                return event.promote_waitlisted_user()
            return None

    def notify_registrants(self, text: str, notification_type: str):
        from core.services import create_notification

        affected = self.registrations.filter(
            status__in=[Registration.Status.REGISTERED, Registration.Status.WAITLISTED]
        ).select_related("user")
        for registration in affected:
            create_notification(
                user=registration.user,
                text=text,
                notification_type=notification_type,
                event=self,
            )

    def attendance_breakdown(self) -> dict[str, int]:
        counts = self.registrations.aggregate(
            present=Count("id", filter=Q(attendance=Registration.Attendance.PRESENT)),
            absent=Count("id", filter=Q(attendance=Registration.Attendance.ABSENT)),
            not_marked=Count(
                "id", filter=Q(attendance=Registration.Attendance.NOT_MARKED)
            ),
        )
        return counts


class Registration(models.Model):
    class Status(models.TextChoices):
        REGISTERED = "registered", "Registered"
        WAITLISTED = "waitlisted", "Waitlisted"
        CANCELLED = "cancelled", "Cancelled"

    class Attendance(models.TextChoices):
        PRESENT = "present", "Present"
        ABSENT = "absent", "Absent"
        NOT_MARKED = "not_marked", "Not marked"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="registrations")
    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="registrations"
    )
    status = models.CharField(max_length=16, choices=Status.choices)
    attendance = models.CharField(
        max_length=16, choices=Attendance.choices, default=Attendance.NOT_MARKED
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(fields=["event", "user"], name="unique_event_user")
        ]


class Announcement(models.Model):
    class TargetType(models.TextChoices):
        CLUB = "club", "Club"
        EVENT = "event", "Event"
        ROOM = "room", "Room"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    author = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="announcements"
    )
    target_type = models.CharField(max_length=8, choices=TargetType.choices)
    club = models.ForeignKey(
        Club, on_delete=models.CASCADE, null=True, blank=True, related_name="announcements"
    )
    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, null=True, blank=True, related_name="announcements"
    )
    room = models.ForeignKey(
        "rooms.DiscussionRoom",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="announcements",
    )
    title = models.CharField(max_length=120)
    body = models.TextField(max_length=1200)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def clean(self):
        super().clean()
        target_count = sum(bool(x) for x in [self.club, self.event, self.room])
        if target_count != 1:
            raise ValidationError("Announcement must target exactly one object.")
