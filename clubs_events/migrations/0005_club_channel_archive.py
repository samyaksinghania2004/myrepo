from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("clubs_events", "0004_club_channel_members"),
    ]

    operations = [
        migrations.AddField(
            model_name="clubchannel",
            name="is_archived",
            field=models.BooleanField(default=False),
        ),
    ]
