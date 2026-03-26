from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0004_direct_messages"),
    ]

    operations = [
        migrations.CreateModel(
            name="DirectMessageBlock",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(default=timezone.now)),
                ("blocked", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="blocked_by_users", to="accounts.user")),
                ("blocker", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="blocked_users", to="accounts.user")),
            ],
        ),
        migrations.AddConstraint(
            model_name="directmessageblock",
            constraint=models.UniqueConstraint(fields=("blocker", "blocked"), name="unique_dm_block_pair"),
        ),
    ]
