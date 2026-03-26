from __future__ import annotations

from typing import Optional

from django.utils.text import slugify

from .models import Club, ClubChannel, ClubMessage, Event


DEFAULT_CHANNELS = [
    {
        "name": "announcements",
        "slug": "announcements",
        "channel_type": ClubChannel.ChannelType.ANNOUNCEMENTS,
        "is_private": False,
        "is_read_only": True,
    },
    {
        "name": "welcome",
        "slug": "welcome",
        "channel_type": ClubChannel.ChannelType.WELCOME,
        "is_private": False,
        "is_read_only": True,
    },
    {
        "name": "main",
        "slug": "main",
        "channel_type": ClubChannel.ChannelType.MAIN,
        "is_private": False,
        "is_read_only": False,
    },
]


def _unique_channel_slug(club: Club, base: str) -> str:
    base = slugify(base)[:60] or "channel"
    slug = base
    counter = 2
    while ClubChannel.objects.filter(club=club, slug=slug).exists():
        slug = f"{base}-{counter}"
        counter += 1
    return slug


def ensure_default_channels(club: Club, actor=None) -> None:
    for channel_data in DEFAULT_CHANNELS:
        channel, created = ClubChannel.objects.get_or_create(
            club=club,
            slug=channel_data["slug"],
            defaults={
                "name": channel_data["name"],
                "channel_type": channel_data["channel_type"],
                "is_private": channel_data["is_private"],
                "is_read_only": channel_data["is_read_only"],
                "created_by": actor,
            },
        )
        if not created and channel.is_archived:
            channel.is_archived = False
            channel.save(update_fields=["is_archived", "updated_at"])


def get_or_create_event_channel(event: Event, actor=None) -> Optional[ClubChannel]:
    ensure_default_channels(event.club, actor=actor)
    slug = f"event-{event.pk.hex[:8]}"
    channel = ClubChannel.objects.filter(club=event.club, event=event).first()
    if channel:
        if channel.is_archived:
            return None
    else:
        channel = ClubChannel.objects.create(
            club=event.club,
            event=event,
            name=event.title,
            slug=slug,
            channel_type=ClubChannel.ChannelType.EVENT,
            is_private=False,
            is_read_only=False,
            created_by=actor,
        )
    update_fields = []
    if channel.name != event.title:
        channel.name = event.title
        update_fields.append("name")
    if channel.channel_type != ClubChannel.ChannelType.EVENT:
        channel.channel_type = ClubChannel.ChannelType.EVENT
        update_fields.append("channel_type")
    if channel.is_private:
        channel.is_private = False
        update_fields.append("is_private")
    if channel.is_read_only:
        channel.is_read_only = False
        update_fields.append("is_read_only")
    if update_fields:
        update_fields.append("updated_at")
        channel.save(update_fields=update_fields)
    return channel


def create_welcome_message(club: Club, user) -> None:
    ensure_default_channels(club, actor=None)
    channel = ClubChannel.objects.filter(
        club=club, channel_type=ClubChannel.ChannelType.WELCOME, is_archived=False
    ).first()
    if not channel:
        return
    ClubMessage.objects.create(
        channel=channel,
        author=user,
        text=f"{user.display_name} joined the club.",
        is_system=True,
    )


def create_custom_channel(club: Club, name: str, *, is_private: bool, actor=None) -> ClubChannel:
    slug = _unique_channel_slug(club, name)
    return ClubChannel.objects.create(
        club=club,
        name=name,
        slug=slug,
        channel_type=ClubChannel.ChannelType.CUSTOM,
        is_private=is_private,
        is_read_only=False,
        created_by=actor,
    )
