from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from core.models import Notification

from .models import Club, Event, Registration


class EventRegistrationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user1 = User.objects.create_user(
            username="user1",
            email="user1@iitk.ac.in",
            password="StrongPass@123",
        )
        self.user2 = User.objects.create_user(
            username="user2",
            email="user2@iitk.ac.in",
            password="StrongPass@123",
        )
        self.rep = User.objects.create_user(
            username="rep1",
            email="rep1@iitk.ac.in",
            password="StrongPass@123",
            role=User.Role.CLUB_REP,
        )
        self.club = Club.objects.create(
            name="Programming Club",
            category="Technical",
            description="Coding club",
            contact_email="progclub@iitk.ac.in",
        )
        self.club.representatives.add(self.rep)
        self.event = Event.objects.create(
            club=self.club,
            title="Bootcamp",
            description="Description",
            venue="LHC",
            start_time=timezone.now() + timedelta(days=1),
            end_time=timezone.now() + timedelta(days=1, hours=2),
            capacity=1,
            status=Event.Status.PUBLISHED,
            waitlist_enabled=True,
            created_by=self.rep,
            updated_by=self.rep,
        )

    def test_register_waitlist_and_promotion(self):
        reg1 = self.event.register_user(self.user1)
        reg2 = self.event.register_user(self.user2)

        self.assertEqual(reg1.status, Registration.Status.REGISTERED)
        self.assertEqual(reg2.status, Registration.Status.WAITLISTED)

        self.event.cancel_registration_for_user(self.user1)
        reg2.refresh_from_db()
        self.assertEqual(reg2.status, Registration.Status.REGISTERED)
        self.assertTrue(
            Notification.objects.filter(
                user=self.user2,
                notification_type=Notification.Type.WAITLIST_PROMOTED,
            ).exists()
        )
