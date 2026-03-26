from django.db import migrations, models
from django.utils import timezone
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_notification_rich_payload"),
    ]

    operations = [
        migrations.CreateModel(
            name="DirectMessageThread",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(default=timezone.now)),
                ("updated_at", models.DateTimeField(default=timezone.now)),
            ],
            options={
                "ordering": ["-updated_at"],
            },
        ),
        migrations.CreateModel(
            name="DirectMessage",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("body", models.TextField(max_length=2000)),
                ("created_at", models.DateTimeField(default=timezone.now)),
                ("sender", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="direct_messages", to="accounts.user")),
                ("thread", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="messages", to="core.directmessagethread")),
            ],
            options={
                "ordering": ["created_at"],
            },
        ),
        migrations.CreateModel(
            name="DirectMessageParticipant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("last_read_at", models.DateTimeField(blank=True, null=True)),
                ("joined_at", models.DateTimeField(default=timezone.now)),
                ("thread", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="participants_meta", to="core.directmessagethread")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="direct_message_participations", to="accounts.user")),
            ],
        ),
        migrations.AddField(
            model_name="directmessagethread",
            name="participants",
            field=models.ManyToManyField(related_name="direct_message_threads", through="core.DirectMessageParticipant", to="accounts.user"),
        ),
        migrations.AddConstraint(
            model_name="directmessageparticipant",
            constraint=models.UniqueConstraint(fields=("thread", "user"), name="unique_dm_thread_participant"),
        ),
    ]
