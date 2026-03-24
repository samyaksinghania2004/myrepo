from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import AuditLogEntry, Notification
from clubs_events.models import Club

from .forms import ModerateReportForm
from .models import DiscussionRoom, Message, Report, RoomHandle


class RoomFlowTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.student = User.objects.create_user(
            username="student",
            email="student@iitk.ac.in",
            password="StrongPass@123",
        )
        self.moderator = User.objects.create_user(
            username="moderator",
            email="moderator@iitk.ac.in",
            password="StrongPass@123",
            role=User.Role.MODERATOR,
        )
        self.club = Club.objects.create(
            name="Music Club",
            category="Cultural",
            description="Music club",
            contact_email="music@iitk.ac.in",
        )
        self.room = DiscussionRoom.objects.create(
            name="Open Room",
            description="General room",
            room_type=DiscussionRoom.RoomType.TOPIC,
            access_type=DiscussionRoom.AccessType.PUBLIC,
            created_by=self.moderator,
        )
        self.room.moderators.add(self.moderator)

    def test_public_join_creates_approved_handle(self):
        self.client.login(username="student", password="StrongPass@123")
        response = self.client.post(
            reverse("rooms:join_room", args=[self.room.pk]),
            {"handle_name": "CuriousFresher"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        handle = RoomHandle.objects.get(room=self.room, user=self.student)
        self.assertEqual(handle.status, RoomHandle.Status.APPROVED)

    def test_moderation_delete_and_mute(self):
        handle = RoomHandle.objects.create(
            room=self.room,
            user=self.student,
            handle_name="CuriousFresher",
            status=RoomHandle.Status.APPROVED,
        )
        message = Message.objects.create(room=self.room, handle=handle, text="Abusive text")
        report = Report.objects.create(message=message, reporter=self.student, reason="Abuse")

        self.client.login(username="moderator", password="StrongPass@123")
        response = self.client.post(
            reverse("rooms:moderate_report", args=[report.pk]),
            {
                "action": ModerateReportForm.ACTION_DELETE_AND_MUTE,
                "reason": "Code of conduct violation",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        report.refresh_from_db()
        message.refresh_from_db()
        handle.refresh_from_db()

        self.assertEqual(report.status, Report.Status.ACTION_TAKEN)
        self.assertTrue(message.is_deleted)
        self.assertTrue(handle.is_muted)
        self.assertTrue(
            AuditLogEntry.objects.filter(
                action_type=AuditLogEntry.ActionType.DELETE_AND_MUTE,
                target_user=self.student,
            ).exists()
        )
        self.assertTrue(
            Notification.objects.filter(
                user=self.student,
                notification_type=Notification.Type.MODERATION_ACTION,
            ).exists()
        )
