from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from clubs_events.models import Club, ClubMembership, Event, Registration

from .models import DiscussionRoom, Message, Report, RoomHandle, RoomInvite


class RoomPermissionAndInviteTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user(username="admin", email="admin@iitk.ac.in", password="StrongPass@123", role=User.Role.INSTITUTE_ADMIN)
        self.coord = User.objects.create_user(username="coord", email="coord@iitk.ac.in", password="StrongPass@123")
        self.secretary = User.objects.create_user(username="sec", email="sec@iitk.ac.in", password="StrongPass@123")
        self.student = User.objects.create_user(username="student", email="student@iitk.ac.in", password="StrongPass@123")
        self.club = Club.objects.create(name="Music Club", category="Cultural", description="Music club", contact_email="music@iitk.ac.in")
        ClubMembership.objects.create(club=self.club, user=self.coord, status="active", local_role="coordinator")
        ClubMembership.objects.create(club=self.club, user=self.secretary, status="active", local_role="secretary")
        ClubMembership.objects.create(club=self.club, user=self.student, status="active", local_role="member")
        self.event = Event.objects.create(club=self.club, title="Jam", description="j", venue="a", start_time=timezone.now()+timedelta(days=1), end_time=timezone.now()+timedelta(days=1, hours=1), status="published", created_by=self.coord)
        Registration.objects.create(event=self.event, user=self.student, status="registered")

    def test_any_user_can_create_open_room(self):
        self.client.login(username="student", password="StrongPass@123")
        resp = self.client.post(
            reverse("rooms:room_create"),
            {"name": "Open Room", "description": "d", "access_type": "public"},
        )
        self.assertEqual(resp.status_code, 302)

    def test_private_invite_only_access_flow(self):
        room = DiscussionRoom.objects.create(
            name="Private",
            description="d",
            room_type="topic",
            access_type="private_invite_only",
            created_by=self.coord,
        )
        self.client.login(username="student", password="StrongPass@123")
        self.assertEqual(self.client.get(reverse("rooms:join_room", args=[room.pk])).status_code, 403)
        self.client.login(username="coord", password="StrongPass@123")
        self.client.post(
            reverse("rooms:invite_user", args=[room.pk]),
            {"identifier": self.student.email},
        )
        invite = RoomInvite.objects.get(room=room, recipient=self.student)
        self.client.login(username="student", password="StrongPass@123")
        self.assertEqual(
            self.client.get(reverse("rooms:join_room", args=[room.pk])).status_code,
            200,
        )
        resp = self.client.post(reverse("rooms:join_room", args=[room.pk]), {"handle_name": "invitee"})
        self.assertEqual(resp.status_code, 302)
        invite.refresh_from_db()
        self.assertEqual(invite.status, RoomInvite.Status.ACCEPTED)

    def test_private_room_requires_fresh_invite_after_leaving(self):
        room = DiscussionRoom.objects.create(
            name="Private",
            description="d",
            room_type="topic",
            access_type="private_invite_only",
            created_by=self.coord,
        )
        self.client.login(username="coord", password="StrongPass@123")
        self.client.post(
            reverse("rooms:invite_user", args=[room.pk]),
            {"identifier": self.student.email},
        )
        invite = RoomInvite.objects.get(room=room, recipient=self.student)
        self.client.login(username="student", password="StrongPass@123")
        self.client.post(reverse("rooms:join_room", args=[room.pk]), {"handle_name": "invitee"})
        self.client.post(reverse("rooms:leave_room", args=[room.pk]))
        self.assertEqual(self.client.get(reverse("rooms:join_room", args=[room.pk])).status_code, 403)
        invite.refresh_from_db()
        self.assertEqual(invite.status, RoomInvite.Status.REVOKED)

    def test_open_room_limit(self):
        self.client.login(username="student", password="StrongPass@123")
        for idx in range(5):
            DiscussionRoom.objects.create(
                name=f"Room {idx}",
                description="d",
                room_type="topic",
                access_type="public",
                created_by=self.student,
            )
        resp = self.client.post(
            reverse("rooms:room_create"),
            {"name": "Overflow", "description": "d", "access_type": "public"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            DiscussionRoom.objects.filter(
                created_by=self.student,
                room_type="topic",
                is_archived=False,
            ).count(),
            5,
        )

    def test_admin_only_reports_dashboard(self):
        room = DiscussionRoom.objects.create(name="Open Room", description="General room", room_type="topic", access_type="public", created_by=self.coord)
        handle = RoomHandle.objects.create(room=room, user=self.student, handle_name="CuriousFresher", status=RoomHandle.Status.APPROVED)
        message = Message.objects.create(room=room, handle=handle, text="Abusive text")
        Report.objects.create(message=message, reporter=self.student, reason="Abuse")
        self.client.login(username="coord", password="StrongPass@123")
        self.assertEqual(self.client.get(reverse("rooms:moderation_dashboard")).status_code, 403)
        self.client.login(username="admin", password="StrongPass@123")
        self.assertEqual(self.client.get(reverse("rooms:moderation_dashboard")).status_code, 200)
