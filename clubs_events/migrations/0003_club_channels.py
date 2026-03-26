from django.conf import settings
from django.db import migrations, models
import django.utils.timezone
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    dependencies = [
        ("clubs_events", "0002_remove_club_followers_remove_club_representatives_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ClubChannel",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=80)),
                ("slug", models.SlugField(max_length=80)),
                ("channel_type", models.CharField(choices=[("announcements", "Announcements"), ("welcome", "Welcome"), ("main", "Main"), ("random", "Random"), ("events", "Events"), ("event", "Event"), ("custom", "Custom")], default="custom", max_length=20)),
                ("is_private", models.BooleanField(default=False)),
                ("is_read_only", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("club", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="channels", to="clubs_events.club")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_channels", to=settings.AUTH_USER_MODEL)),
                ("event", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="chat_channel", to="clubs_events.event")),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="ClubMessage",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("text", models.TextField(max_length=2000)),
                ("is_system", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("author", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="club_messages", to=settings.AUTH_USER_MODEL)),
                ("channel", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="messages", to="clubs_events.clubchannel")),
            ],
            options={
                "ordering": ["created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="clubchannel",
            constraint=models.UniqueConstraint(fields=("club", "slug"), name="unique_club_channel_slug"),
        ),
    ]
