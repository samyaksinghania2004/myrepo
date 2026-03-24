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

    def test_secretary_can_create_room_in_own_club(self):
        self.client.login(username="sec", password="StrongPass@123")
        resp = self.client.post(reverse("rooms:room_create"), {"name": "Sec Room", "description": "d", "room_type": "club", "access_type": "club_only", "club": str(self.club.pk), "is_archived": False})
        self.assertEqual(resp.status_code, 302)

    def test_private_invite_only_access_flow(self):
        room = DiscussionRoom.objects.create(name="Private", description="d", room_type="event", access_type="private_invite_only", event=self.event, club=self.club, created_by=self.coord)
        self.client.login(username="student", password="StrongPass@123")
        self.assertEqual(self.client.get(reverse("rooms:join_room", args=[room.pk])).status_code, 403)
        self.client.login(username="coord", password="StrongPass@123")
        self.client.post(reverse("rooms:invite_user", args=[room.pk]), {"recipient": self.student.id})
        invite = RoomInvite.objects.get(room=room, recipient=self.student)
        self.client.login(username="student", password="StrongPass@123")
        self.client.get(reverse("rooms:respond_invite", args=[invite.pk, "accept"]))
        resp = self.client.post(reverse("rooms:join_room", args=[room.pk]), {"handle_name": "invitee"})
        self.assertEqual(resp.status_code, 302)

    def test_admin_only_reports_dashboard(self):
        room = DiscussionRoom.objects.create(name="Open Room", description="General room", room_type="topic", access_type="public", created_by=self.coord)
        handle = RoomHandle.objects.create(room=room, user=self.student, handle_name="CuriousFresher", status=RoomHandle.Status.APPROVED)
        message = Message.objects.create(room=room, handle=handle, text="Abusive text")
        Report.objects.create(message=message, reporter=self.student, reason="Abuse")
        self.client.login(username="coord", password="StrongPass@123")
        self.assertEqual(self.client.get(reverse("rooms:moderation_dashboard")).status_code, 403)
        self.client.login(username="admin", password="StrongPass@123")
        self.assertEqual(self.client.get(reverse("rooms:moderation_dashboard")).status_code, 200)
