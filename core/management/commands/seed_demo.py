from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from clubs_events.models import Club, ClubMembership, Event, Registration
from rooms.models import DiscussionRoom, Message, RoomHandle


class Command(BaseCommand):
    help = "Create demo users, clubs, events, registrations and discussion rooms."

    def handle(self, *args, **options):
        User = get_user_model()

        users = {
            "student": {
                "username": "student1",
                "email": "student1@iitk.ac.in",
                "role": User.Role.STUDENT,
                "password": "Password@123",
            },
            "coordinator": {
                "username": "coordinator1",
                "email": "coordinator1@iitk.ac.in",
                "role": User.Role.STUDENT,
                "password": "Password@123",
            },
            "admin": {
                "username": "admin1",
                "email": "admin1@iitk.ac.in",
                "role": User.Role.INSTITUTE_ADMIN,
                "password": "Password@123",
                "is_staff": True,
                "is_superuser": True,
            },
        }

        created_users = {}
        for key, payload in users.items():
            password = payload.pop("password")
            user, _ = User.objects.get_or_create(username=payload["username"], defaults=payload)
            for field, value in payload.items():
                setattr(user, field, value)
            user.set_password(password)
            user.save()
            created_users[key] = user

        club, _ = Club.objects.get_or_create(
            name="Programming Club",
            defaults={
                "category": "Technical",
                "description": "Talks, workshops and contests for coding enthusiasts.",
                "contact_email": "progclub@iitk.ac.in",
            },
        )
        ClubMembership.objects.update_or_create(
            club=club,
            user=created_users["coordinator"],
            defaults={"status": "active", "local_role": "coordinator"},
        )
        ClubMembership.objects.update_or_create(
            club=club,
            user=created_users["student"],
            defaults={"status": "active", "local_role": "member"},
        )

        now = timezone.now()
        event, _ = Event.objects.get_or_create(
            club=club,
            title="CP Bootcamp – Intro to DP",
            defaults={
                "description": "Hands-on workshop on classical dynamic programming problems.",
                "venue": "L-16, Lecture Hall Complex",
                "start_time": now + timedelta(days=3),
                "end_time": now + timedelta(days=3, hours=2),
                "capacity": 2,
                "tags": "CP, workshop",
                "status": Event.Status.PUBLISHED,
                "waitlist_enabled": True,
                "created_by": created_users["coordinator"],
                "updated_by": created_users["coordinator"],
            },
        )
        Registration.objects.get_or_create(
            event=event,
            user=created_users["student"],
            defaults={"status": Registration.Status.REGISTERED},
        )

        room, _ = DiscussionRoom.objects.get_or_create(
            name="Competitive Programming @ IITK",
            defaults={
                "description": "Discuss problems, contests and resources.",
                "room_type": DiscussionRoom.RoomType.TOPIC,
                "access_type": DiscussionRoom.AccessType.PUBLIC,
                "created_by": created_users["coordinator"],
            },
        )

        handle, _ = RoomHandle.objects.get_or_create(
            room=room,
            user=created_users["student"],
            defaults={
                "handle_name": "CuriousFresher",
                "status": RoomHandle.Status.APPROVED,
                "approved_at": timezone.now(),
            },
        )
        Message.objects.get_or_create(
            room=room,
            handle=handle,
            text="Is there any good resource for DP on trees?",
        )

        self.stdout.write(self.style.SUCCESS("Demo data loaded successfully."))
