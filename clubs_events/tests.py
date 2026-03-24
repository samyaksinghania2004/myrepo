from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Notification

from .models import Announcement, Club, ClubMembership, Event, Registration


class ClubMembershipAndPermissionsTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.student = User.objects.create_user(username="s", email="s@iitk.ac.in", password="Pass@123")
        self.coord = User.objects.create_user(username="c", email="c@iitk.ac.in", password="Pass@123")
        self.secretary = User.objects.create_user(username="sec", email="sec@iitk.ac.in", password="Pass@123")
        self.admin = User.objects.create_user(username="a", email="a@iitk.ac.in", password="Pass@123", role=User.Role.INSTITUTE_ADMIN)
        self.club = Club.objects.create(name="Programming Club", category="Tech", description="d", contact_email="x@iitk.ac.in")
        ClubMembership.objects.create(club=self.club, user=self.coord, status="active", local_role="coordinator")
        ClubMembership.objects.create(club=self.club, user=self.secretary, status="active", local_role="secretary")

    def test_join_leave_and_rejoin_resets_local_role(self):
        self.client.login(username="s", password="Pass@123")
        self.client.post(reverse("clubs_events:club_join", args=[self.club.pk]))
        membership = ClubMembership.objects.get(club=self.club, user=self.student)
        self.assertEqual(membership.local_role, "member")
        membership.local_role = "secretary"
        membership.save(update_fields=["local_role"])
        self.client.post(reverse("clubs_events:club_leave", args=[self.club.pk]))
        membership.refresh_from_db()
        self.assertEqual(membership.local_role, "member")
        self.assertEqual(membership.status, "left")
        self.client.post(reverse("clubs_events:club_join", args=[self.club.pk]))
        membership.refresh_from_db()
        self.assertEqual(membership.local_role, "member")
        self.assertEqual(membership.status, "active")

    def test_only_admin_can_create_club(self):
        self.client.login(username="s", password="Pass@123")
        resp = self.client.post(reverse("clubs_events:club_create"), {"name": "X", "category": "y", "description": "z", "contact_email": "x@iitk.ac.in", "is_active": True})
        self.assertEqual(resp.status_code, 403)
        self.client.login(username="a", password="Pass@123")
        resp = self.client.post(reverse("clubs_events:club_create"), {"name": "Y", "category": "y", "description": "z", "contact_email": "x2@iitk.ac.in", "is_active": True})
        self.assertEqual(resp.status_code, 302)

    def test_coordinator_and_secretary_can_create_event_for_own_club(self):
        self.client.login(username="c", password="Pass@123")
        payload = {"club": str(self.club.pk), "title": "t", "description": "d", "venue": "v", "start_time": (timezone.now()+timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"), "end_time": (timezone.now()+timedelta(days=1,hours=1)).strftime("%Y-%m-%dT%H:%M"), "capacity": 10, "tags": "x", "status": "published", "waitlist_enabled": True, "is_archived": False}
        self.assertEqual(self.client.post(reverse("clubs_events:event_create"), payload).status_code, 302)
        self.client.login(username="sec", password="Pass@123")
        payload["title"] = "t2"
        self.assertEqual(self.client.post(reverse("clubs_events:event_create"), payload).status_code, 302)

    def test_coordinator_can_assign_revoke_secretary_secretary_cannot(self):
        newbie = get_user_model().objects.create_user(username="n", email="n@iitk.ac.in", password="Pass@123")
        ClubMembership.objects.create(club=self.club, user=newbie, status="active", local_role="member")
        self.client.login(username="c", password="Pass@123")
        self.assertEqual(self.client.get(reverse("clubs_events:assign_secretary", args=[self.club.pk, newbie.id])).status_code, 302)
        self.client.login(username="sec", password="Pass@123")
        self.assertEqual(self.client.get(reverse("clubs_events:revoke_secretary", args=[self.club.pk, newbie.id])).status_code, 403)

    def test_announcement_notification(self):
        attendee = get_user_model().objects.create_user(username="u", email="u@iitk.ac.in", password="Pass@123")
        event = Event.objects.create(club=self.club, title="E", description="d", venue="v", start_time=timezone.now()+timedelta(days=1), end_time=timezone.now()+timedelta(days=1,hours=1), status="published", created_by=self.coord)
        Registration.objects.create(event=event, user=attendee, status="registered")
        self.client.login(username="c", password="Pass@123")
        response = self.client.post(reverse("clubs_events:announcement_create", args=["event", event.pk]), {"title": "Heads up", "body": "Bring ID"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Announcement.objects.filter(event=event).exists())
        self.assertTrue(Notification.objects.filter(user=attendee, notification_type=Notification.Type.ANNOUNCEMENT).exists())
