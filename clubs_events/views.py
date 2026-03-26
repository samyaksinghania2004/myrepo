from __future__ import annotations

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Prefetch, Q
from django.http import Http404, HttpResponseForbidden, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.formats import date_format
from django.utils.html import escape
from django.template.defaultfilters import linebreaksbr

from core.models import AuditLogEntry, Notification
from core.permissions import (
    can_archive_or_delete_club,
    can_assign_secretary,
    can_create_club,
    can_create_event,
    can_manage_club,
    can_manage_event,
    can_post_announcement,
    is_global_admin,
)
from core.services import create_notification, log_audit
from rooms.models import DiscussionRoom, RoomHandle

from .forms import (
    AnnouncementForm,
    ClubChannelForm,
    ClubChannelMemberForm,
    ClubForm,
    ClubMessageForm,
    EventCancellationForm,
    EventForm,
)
from .models import (
    Announcement,
    Club,
    ClubChannel,
    ClubChannelMember,
    ClubMembership,
    ClubMessage,
    Event,
    Registration,
)
from .services import (
    create_custom_channel,
    create_welcome_message,
    ensure_default_channels,
    get_or_create_event_channel,
)


def _clubs_user_can_create_for(user):
    if is_global_admin(user):
        return Club.objects.filter(is_active=True)
    return Club.objects.filter(
        memberships__user=user,
        memberships__status=ClubMembership.Status.ACTIVE,
        memberships__local_role__in=[
            ClubMembership.LocalRole.COORDINATOR,
            ClubMembership.LocalRole.SECRETARY,
        ],
        is_active=True,
    ).distinct()


@login_required
def event_feed_view(request):
    Event.objects.filter(
        status=Event.Status.PUBLISHED,
        end_time__lt=timezone.now(),
    ).update(status=Event.Status.COMPLETED)

    q = request.GET.get("q", "").strip()[:50]
    selected_club = request.GET.get("club", "").strip()
    tag = request.GET.get("tag", "").strip()[:50]
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()

    clubs = Club.objects.filter(is_active=True).order_by("name")
    events = Event.objects.select_related("club").filter(
        status=Event.Status.PUBLISHED,
        end_time__gte=timezone.now(),
        is_archived=False,
        club__is_active=True,
    )
    if q:
        events = events.filter(Q(title__icontains=q) | Q(description__icontains=q))
    if selected_club:
        events = events.filter(club_id=selected_club)
    if tag:
        events = events.filter(tags__icontains=tag)
    if date_from:
        events = events.filter(start_time__date__gte=date_from)
    if date_to:
        events = events.filter(start_time__date__lte=date_to)

    member_club_ids = request.user.club_memberships.filter(
        status=ClubMembership.Status.ACTIVE
    ).values_list("club_id", flat=True)
    followed_events = (
        Event.objects.select_related("club")
        .filter(
            club_id__in=member_club_ids,
            status=Event.Status.PUBLISHED,
            end_time__gte=timezone.now(),
            is_archived=False,
        )
        .exclude(pk__in=events.values_list("pk", flat=True))[:5]
    )
    my_registrations = (
        request.user.registrations.select_related("event", "event__club")
        .filter(
            status__in=[Registration.Status.REGISTERED, Registration.Status.WAITLISTED],
            event__end_time__gte=timezone.now(),
        )[:6]
    )

    events = list(events)
    for event in events:
        channel = get_or_create_event_channel(event, actor=request.user)
        if channel:
            event.discuss_url = reverse(
                "clubs_events:club_channel",
                kwargs={"pk": event.club_id, "slug": channel.slug},
            )
        else:
            event.discuss_url = None

    return render(
        request,
        "clubs_events/event_feed.html",
        {
            "events": events,
            "clubs": clubs,
            "selected_club": selected_club,
            "tag": tag,
            "date_from": date_from,
            "date_to": date_to,
            "q": q,
            "my_registrations": my_registrations,
            "followed_events": followed_events,
            "can_create_event_any": _clubs_user_can_create_for(request.user).exists(),
        },
    )


@login_required
def club_list_view(request):
    q = request.GET.get("q", "").strip()[:50]
    clubs = Club.objects.filter(is_active=True)
    if q:
        clubs = clubs.filter(Q(name__icontains=q) | Q(category__icontains=q))
    active_membership_ids = set(
        request.user.club_memberships.filter(status=ClubMembership.Status.ACTIVE).values_list(
            "club_id", flat=True
        )
    )
    manageable_club_ids = set(
        request.user.club_memberships.filter(
            status=ClubMembership.Status.ACTIVE,
            local_role=ClubMembership.LocalRole.COORDINATOR,
        ).values_list("club_id", flat=True)
    )
    return render(
        request,
        "clubs_events/club_list.html",
        {
            "clubs": clubs,
            "q": q,
            "active_membership_ids": active_membership_ids,
            "manageable_club_ids": manageable_club_ids,
            "can_create_club": can_create_club(request.user),
        },
    )


def _serialize_club_message(message):
    created_at = timezone.localtime(message.created_at)
    author_name = message.author.display_name if message.author else "System"
    body_html = str(linebreaksbr(escape(message.text)))
    return {
        "id": str(message.id),
        "author_name": author_name,
        "created_at": message.created_at.isoformat(),
        "created_at_display": date_format(created_at, "DATETIME_FORMAT"),
        "body_html": body_html,
        "is_system": message.is_system,
    }


def _get_club_channel_access(user, club, channel):
    membership = ClubMembership.objects.filter(
        club=club, user=user, status=ClubMembership.Status.ACTIVE
    ).first()
    is_member = bool(membership)
    is_coordinator = bool(
        membership and membership.local_role == ClubMembership.LocalRole.COORDINATOR
    )
    is_secretary = bool(
        membership and membership.local_role == ClubMembership.LocalRole.SECRETARY
    )
    is_admin = is_global_admin(user)
    can_manage_channels = is_admin or is_coordinator
    allowed_private_channel_ids = set()
    if not can_manage_channels:
        allowed_private_channel_ids = set(
            ClubChannelMember.objects.filter(channel__club=club, user=user).values_list(
                "channel_id", flat=True
            )
        )

    if channel.is_private:
        if not is_member and not can_manage_channels:
            return None
        if not can_manage_channels and channel.id not in allowed_private_channel_ids:
            return None
    if (
        channel.channel_type == ClubChannel.ChannelType.EVENT
        and channel.event
        and channel.event.status != Event.Status.PUBLISHED
        and not (is_member or is_admin)
    ):
        return None

    def can_access_channel():
        if not channel.is_private:
            return True
        if can_manage_channels:
            return True
        if not is_member:
            return False
        return channel.id in allowed_private_channel_ids

    def can_post_to_channel():
        if not can_access_channel():
            return False
        if not (is_member or is_admin):
            return False
        if channel.channel_type == ClubChannel.ChannelType.WELCOME:
            return False
        if channel.channel_type == ClubChannel.ChannelType.ANNOUNCEMENTS:
            return is_admin or is_coordinator or is_secretary
        if channel.is_read_only:
            return False
        return True

    return {
        "is_member": is_member,
        "is_admin": is_admin,
        "is_coordinator": is_coordinator,
        "is_secretary": is_secretary,
        "can_manage_channels": can_manage_channels,
        "can_access": can_access_channel(),
        "can_post": can_post_to_channel(),
    }


@login_required
def club_detail_view(request, pk, slug=None):
    club = get_object_or_404(Club, pk=pk)
    membership = ClubMembership.objects.filter(
        club=club, user=request.user, status=ClubMembership.Status.ACTIVE
    ).first()
    members = (
        club.memberships.filter(status=ClubMembership.Status.ACTIVE)
        .select_related("user")
        .order_by("user__username")
    )
    is_member = bool(membership)
    is_coordinator = bool(
        membership and membership.local_role == ClubMembership.LocalRole.COORDINATOR
    )
    is_secretary = bool(
        membership and membership.local_role == ClubMembership.LocalRole.SECRETARY
    )
    is_admin = is_global_admin(request.user)
    can_manage_channels = is_admin or is_coordinator
    ensure_default_channels(club, actor=request.user)
    for event in club.events.filter(is_archived=False):
        get_or_create_event_channel(event, actor=request.user)

    allowed_private_channel_ids = set()
    if not can_manage_channels:
        allowed_private_channel_ids = set(
            ClubChannelMember.objects.filter(
                channel__club=club, user=request.user
            ).values_list("channel_id", flat=True)
        )

    channels_qs = ClubChannel.objects.filter(club=club, is_archived=False).select_related(
        "event"
    )
    channels = []
    for channel in channels_qs:
        if channel.is_private:
            if not is_member and not can_manage_channels:
                continue
            if not can_manage_channels and channel.id not in allowed_private_channel_ids:
                continue
        if (
            channel.channel_type == ClubChannel.ChannelType.EVENT
            and channel.event
            and channel.event.status != Event.Status.PUBLISHED
            and not (is_member or is_admin)
        ):
            continue
        channels.append(channel)

    if slug:
        active_channel = next((c for c in channels if c.slug == slug), None)
        if active_channel is None:
            raise Http404
    else:
        active_channel = next(
            (c for c in channels if c.channel_type == ClubChannel.ChannelType.MAIN),
            None,
        )
        if active_channel is None and channels:
            active_channel = channels[0]

    if active_channel is None:
        raise Http404

    default_channel_types = {
        ClubChannel.ChannelType.ANNOUNCEMENTS,
        ClubChannel.ChannelType.WELCOME,
        ClubChannel.ChannelType.MAIN,
    }
    can_delete_channel = can_manage_channels and (
        active_channel.channel_type not in default_channel_types
    )
    show_channel_menu = can_delete_channel

    channel_order = {
        ClubChannel.ChannelType.ANNOUNCEMENTS: 0,
        ClubChannel.ChannelType.WELCOME: 1,
        ClubChannel.ChannelType.MAIN: 2,
        ClubChannel.ChannelType.RANDOM: 3,
        ClubChannel.ChannelType.EVENTS: 4,
        ClubChannel.ChannelType.CUSTOM: 5,
    }
    core_channels = sorted(
        [c for c in channels if c.channel_type != ClubChannel.ChannelType.EVENT],
        key=lambda c: (channel_order.get(c.channel_type, 99), c.name.lower()),
    )
    event_channels = sorted(
        [c for c in channels if c.channel_type == ClubChannel.ChannelType.EVENT],
        key=lambda c: c.name.lower(),
    )

    can_create_channel = is_global_admin(request.user) or is_coordinator
    can_manage_members = is_admin or is_coordinator
    show_members = is_member or is_admin
    online_members = []
    offline_members = []
    if show_members:
        online_cutoff = timezone.now() - timedelta(minutes=5)
        for member in members:
            last_seen = member.user.last_seen_at
            if last_seen and last_seen >= online_cutoff:
                online_members.append(member)
            else:
                offline_members.append(member)

    def can_access_channel(channel):
        if not channel.is_private:
            return True
        if can_manage_channels:
            return True
        if not is_member:
            return False
        return channel.id in allowed_private_channel_ids

    def can_post_to_channel():
        if not can_access_channel(active_channel):
            return False
        if not (is_member or is_global_admin(request.user)):
            return False
        if active_channel.channel_type == ClubChannel.ChannelType.WELCOME:
            return False
        if active_channel.channel_type == ClubChannel.ChannelType.ANNOUNCEMENTS:
            return is_admin or is_coordinator or is_secretary
        if active_channel.is_read_only:
            return False
        return True

    form = ClubMessageForm(request.POST or None)
    if request.method == "POST":
        if not can_post_to_channel():
            messages.error(request, "Join the club to send messages in this channel.")
            return redirect("clubs_events:club_channel", pk=club.pk, slug=active_channel.slug)
        if form.is_valid():
            ClubMessage.objects.create(
                channel=active_channel,
                author=request.user,
                text=form.cleaned_data["text"],
            )
            return redirect("clubs_events:club_channel", pk=club.pk, slug=active_channel.slug)

    messages_qs = active_channel.messages.select_related("author")
    last_message_at = messages_qs.last().created_at if messages_qs else None
    can_view_private_members = active_channel.is_private and can_access_channel(active_channel)
    can_add_private_members = active_channel.is_private and can_manage_channels
    if can_view_private_members:
        show_channel_menu = True
    channel_member_form = None
    channel_members = None
    if can_view_private_members:
        channel_members = active_channel.memberships.select_related("user").order_by(
            "user__username"
        )
    if can_add_private_members:
        channel_member_form = ClubChannelMemberForm(club=club)

    return render(
        request,
        "clubs_events/club_detail.html",
        {
            "club": club,
            "membership": membership,
            "members": members,
            "core_channels": core_channels,
            "event_channels": event_channels,
            "active_channel": active_channel,
            "messages_qs": messages_qs,
            "form": form,
            "is_member": is_member,
            "can_create_channel": can_create_channel,
            "can_post_messages": can_post_to_channel(),
            "can_manage_club": can_manage_club(request.user, club),
            "can_manage_members": can_manage_members,
            "can_delete_channel": can_delete_channel,
            "can_create_event_for_club": can_create_event(request.user, club),
            "channel_member_form": channel_member_form,
            "channel_members": channel_members,
            "show_members": show_members,
            "online_members": online_members,
            "offline_members": offline_members,
            "can_view_private_members": can_view_private_members,
            "can_add_private_members": can_add_private_members,
            "show_channel_menu": show_channel_menu,
            "last_message_at": last_message_at,
        },
    )


@login_required
def club_channel_messages_view(request, pk, slug):
    club = get_object_or_404(Club, pk=pk)
    channel = get_object_or_404(
        ClubChannel.objects.select_related("event"),
        club=club,
        slug=slug,
        is_archived=False,
    )
    access = _get_club_channel_access(request.user, club, channel)
    if not access or not access["can_access"]:
        return JsonResponse({"error": "not_allowed"}, status=403)
    messages_qs = channel.messages.select_related("author")
    since = request.GET.get("since", "").strip()
    if since:
        parsed = parse_datetime(since)
        if parsed:
            if timezone.is_naive(parsed):
                parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
            messages_qs = messages_qs.filter(created_at__gt=parsed)
    items = [_serialize_club_message(message) for message in messages_qs]
    return JsonResponse({"items": items})


@login_required
def club_channel_send_view(request, pk, slug):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    club = get_object_or_404(Club, pk=pk)
    channel = get_object_or_404(
        ClubChannel.objects.select_related("event"),
        club=club,
        slug=slug,
        is_archived=False,
    )
    access = _get_club_channel_access(request.user, club, channel)
    if not access or not access["can_post"]:
        return JsonResponse({"error": "not_allowed"}, status=403)
    form = ClubMessageForm(request.POST)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors}, status=400)
    message = ClubMessage.objects.create(
        channel=channel,
        author=request.user,
        text=form.cleaned_data["text"],
    )
    return JsonResponse({"item": _serialize_club_message(message)})

@login_required
def club_join_view(request, pk):
    club = get_object_or_404(Club, pk=pk, is_active=True)
    membership, created = ClubMembership.objects.get_or_create(
        club=club,
        user=request.user,
        defaults={
            "status": ClubMembership.Status.ACTIVE,
            "local_role": ClubMembership.LocalRole.MEMBER,
        },
    )
    if not created:
        membership.status = ClubMembership.Status.ACTIVE
        membership.local_role = ClubMembership.LocalRole.MEMBER
        membership.left_at = None
        membership.save(update_fields=["status", "local_role", "left_at", "updated_at"])
    create_welcome_message(club, request.user)
    messages.success(request, f"You joined {club.name}.")
    log_audit(
        action_type=AuditLogEntry.ActionType.CLUB_JOINED,
        acting_user=request.user,
        details={"club": str(club.id)},
    )
    return redirect("clubs_events:club_detail", pk=club.pk)


@login_required
def club_leave_view(request, pk):
    club = get_object_or_404(Club, pk=pk)
    membership = get_object_or_404(ClubMembership, club=club, user=request.user)
    membership.status = ClubMembership.Status.LEFT
    membership.local_role = ClubMembership.LocalRole.MEMBER
    membership.left_at = timezone.now()
    membership.save(update_fields=["status", "local_role", "left_at", "updated_at"])
    ClubChannelMember.objects.filter(channel__club=club, user=request.user).delete()
    messages.info(request, f"You left {club.name}. If you rejoin later, you will come back as a normal member.")
    log_audit(
        action_type=AuditLogEntry.ActionType.CLUB_LEFT,
        acting_user=request.user,
        details={"club": str(club.id)},
    )
    return redirect("clubs_events:club_detail", pk=club.pk)


@login_required
def club_channel_create_view(request, pk):
    club = get_object_or_404(Club, pk=pk)
    membership = ClubMembership.objects.filter(
        club=club, user=request.user, status=ClubMembership.Status.ACTIVE
    ).first()
    if not (
        is_global_admin(request.user)
        or (membership and membership.local_role == ClubMembership.LocalRole.COORDINATOR)
    ):
        return HttpResponseForbidden("Not allowed")

    form = ClubChannelForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        channel = create_custom_channel(
            club,
            form.cleaned_data["name"],
            is_private=form.cleaned_data["is_private"],
            actor=request.user,
        )
        messages.success(request, f"Channel #{channel.name} created.")
        return redirect("clubs_events:club_channel", pk=club.pk, slug=channel.slug)
    return render(
        request,
        "clubs_events/channel_form.html",
        {"club": club, "form": form},
    )


@login_required
def club_channel_add_member_view(request, pk, slug):
    club = get_object_or_404(Club, pk=pk)
    channel = get_object_or_404(
        ClubChannel, club=club, slug=slug, is_private=True, is_archived=False
    )
    if not can_manage_club(request.user, club):
        return HttpResponseForbidden("Not allowed")
    form = ClubChannelMemberForm(request.POST or None, club=club)
    if request.method == "POST":
        if form.is_valid():
            user = form.cleaned_data["user"]
            member, created = ClubChannelMember.objects.get_or_create(
                channel=channel,
                user=user,
                defaults={"added_by": request.user},
            )
            if created:
                messages.success(
                    request, f"{user.display_name} now has access to #{channel.name}."
                )
            else:
                messages.info(
                    request, f"{user.display_name} already has access to #{channel.name}."
                )
        else:
            for error_list in form.errors.values():
                for error in error_list:
                    messages.error(request, error)
    return redirect("clubs_events:club_channel", pk=club.pk, slug=channel.slug)


@login_required
def club_channel_remove_member_view(request, pk, slug, user_id):
    club = get_object_or_404(Club, pk=pk)
    channel = get_object_or_404(
        ClubChannel, club=club, slug=slug, is_private=True, is_archived=False
    )
    if not can_manage_club(request.user, club):
        return HttpResponseForbidden("Not allowed")
    membership = get_object_or_404(ClubChannelMember, channel=channel, user_id=user_id)
    if request.method == "POST":
        membership.delete()
        messages.success(
            request, f"{membership.user.display_name} removed from #{channel.name}."
        )
    return redirect("clubs_events:club_channel", pk=club.pk, slug=channel.slug)


@login_required
def club_channel_delete_view(request, pk, slug):
    club = get_object_or_404(Club, pk=pk)
    channel = get_object_or_404(ClubChannel, club=club, slug=slug, is_archived=False)
    if not can_manage_club(request.user, club):
        return HttpResponseForbidden("Not allowed")
    if channel.channel_type in [
        ClubChannel.ChannelType.ANNOUNCEMENTS,
        ClubChannel.ChannelType.WELCOME,
        ClubChannel.ChannelType.MAIN,
    ]:
        messages.error(request, "Default channels cannot be deleted.")
        return redirect("clubs_events:club_channel", pk=club.pk, slug=channel.slug)
    if request.method == "POST":
        channel_name = channel.name
        channel.is_archived = True
        channel.save(update_fields=["is_archived", "updated_at"])
        ClubChannelMember.objects.filter(channel=channel).delete()
        messages.success(request, f"#{channel_name} deleted.")
        return redirect("clubs_events:club_detail", pk=club.pk)
    return redirect("clubs_events:club_channel", pk=club.pk, slug=channel.slug)


@login_required
def assign_secretary_view(request, pk, user_id):
    club = get_object_or_404(Club, pk=pk)
    target_membership = get_object_or_404(ClubMembership, club=club, user_id=user_id)
    if not can_assign_secretary(request.user, club, target_membership.user):
        return HttpResponseForbidden("Not allowed")
    target_membership.local_role = ClubMembership.LocalRole.SECRETARY
    target_membership.assigned_by = request.user
    target_membership.save(update_fields=["local_role", "assigned_by", "updated_at"])
    messages.success(request, f"{target_membership.user.display_name} is now a club secretary.")
    log_audit(
        action_type=AuditLogEntry.ActionType.ROLE_GRANTED,
        acting_user=request.user,
        target_user=target_membership.user,
        details={"role": "secretary", "club": str(club.id)},
    )
    return redirect("clubs_events:club_detail", pk=club.pk)


@login_required
def revoke_secretary_view(request, pk, user_id):
    club = get_object_or_404(Club, pk=pk)
    target_membership = get_object_or_404(ClubMembership, club=club, user_id=user_id)
    if not can_assign_secretary(request.user, club, target_membership.user):
        return HttpResponseForbidden("Not allowed")
    target_membership.local_role = ClubMembership.LocalRole.MEMBER
    target_membership.save(update_fields=["local_role", "updated_at"])
    messages.success(request, f"{target_membership.user.display_name} is now a regular member.")
    log_audit(
        action_type=AuditLogEntry.ActionType.ROLE_REVOKED,
        acting_user=request.user,
        target_user=target_membership.user,
        details={"role": "secretary", "club": str(club.id)},
    )
    return redirect("clubs_events:club_detail", pk=club.pk)


@login_required
def club_member_remove_view(request, pk, user_id):
    club = get_object_or_404(Club, pk=pk)
    if not can_manage_club(request.user, club):
        return HttpResponseForbidden("Not allowed")
    if request.method != "POST":
        return redirect("clubs_events:club_detail", pk=club.pk)
    if request.user.id == user_id:
        messages.error(request, "Use the leave action to remove yourself.")
        return redirect("clubs_events:club_detail", pk=club.pk)
    target_membership = get_object_or_404(ClubMembership, club=club, user_id=user_id)
    target_membership.status = ClubMembership.Status.REMOVED
    target_membership.local_role = ClubMembership.LocalRole.MEMBER
    target_membership.left_at = timezone.now()
    target_membership.save(update_fields=["status", "local_role", "left_at", "updated_at"])
    ClubChannelMember.objects.filter(channel__club=club, user_id=user_id).delete()
    messages.success(
        request, f"{target_membership.user.display_name} has been removed from the club."
    )
    log_audit(
        action_type=AuditLogEntry.ActionType.CLUB_MEMBER_REMOVED,
        acting_user=request.user,
        target_user=target_membership.user,
        details={"club": str(club.id)},
    )
    return redirect("clubs_events:club_detail", pk=club.pk)


@login_required
def club_create_view(request):
    if not can_create_club(request.user):
        return HttpResponseForbidden("Only institute or system admins can manage clubs.")
    form = ClubForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        club = form.save()
        ensure_default_channels(club, actor=request.user)
        messages.success(request, "Club created successfully.")
        log_audit(
            action_type=AuditLogEntry.ActionType.CLUB_CREATED,
            acting_user=request.user,
            details={"club": str(club.id)},
        )
        return redirect("clubs_events:club_detail", pk=club.pk)
    return render(request, "clubs_events/club_form.html", {"form": form, "mode": "Create"})


@login_required
def club_edit_view(request, pk):
    club = get_object_or_404(Club, pk=pk)
    if not can_manage_club(request.user, club):
        return HttpResponseForbidden("Not allowed")
    form = ClubForm(request.POST or None, instance=club)
    if request.method == "POST" and form.is_valid():
        club = form.save()
        messages.success(request, "Club updated successfully.")
        log_audit(
            action_type=AuditLogEntry.ActionType.CLUB_UPDATED,
            acting_user=request.user,
            details={"club": str(club.id)},
        )
        return redirect("clubs_events:club_detail", pk=club.pk)
    return render(request, "clubs_events/club_form.html", {"form": form, "mode": "Edit"})


@login_required
def event_detail_view(request, pk):
    event = get_object_or_404(Event.objects.select_related("club"), pk=pk)
    registration = request.user.registrations.filter(event=event).first()
    announcements = event.announcements.filter(is_active=True)[:10]
    event_channel = get_or_create_event_channel(event, actor=request.user)
    discuss_url = None
    if event_channel:
        discuss_url = reverse(
            "clubs_events:club_channel",
            kwargs={"pk": event.club.pk, "slug": event_channel.slug},
        )
    registrations = None
    if can_manage_event(request.user, event):
        registrations = event.registrations.select_related("user").all()
    return render(
        request,
        "clubs_events/event_detail.html",
        {
            "event": event,
            "registration": registration,
            "can_manage_event": can_manage_event(request.user, event),
            "announcements": announcements,
            "can_post_announcement": can_post_announcement(request.user, event=event),
            "registrations": registrations,
            "event_channel": event_channel,
            "discuss_url": discuss_url,
        },
    )


@login_required
def my_events_view(request):
    registrations = request.user.registrations.select_related("event", "event__club").all()
    return render(request, "clubs_events/my_events.html", {"registrations": registrations})


@login_required
def event_create_view(request):
    available_clubs = _clubs_user_can_create_for(request.user)
    if not available_clubs.exists():
        return HttpResponseForbidden("You do not have permission to create events.")
    initial = {}
    if request.GET.get("club"):
        initial["club"] = request.GET.get("club")
    form = EventForm(request.POST or None, club_queryset=available_clubs, initial=initial)
    if request.method == "POST" and form.is_valid():
        if not can_create_event(request.user, form.cleaned_data["club"]):
            return HttpResponseForbidden("You do not have permission to create events.")
        event = form.save(commit=False)
        event.created_by = request.user
        event.updated_by = request.user
        event.save()
        get_or_create_event_channel(event, actor=request.user)
        messages.success(request, "Event created successfully.")
        log_audit(
            action_type=AuditLogEntry.ActionType.EVENT_CREATED,
            acting_user=request.user,
            event=event,
        )
        return redirect("clubs_events:event_detail", pk=event.pk)
    return render(request, "clubs_events/event_form.html", {"form": form, "mode": "Create"})


@login_required
def event_edit_view(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if not can_manage_event(request.user, event):
        raise Http404
    form = EventForm(
        request.POST or None,
        instance=event,
        club_queryset=_clubs_user_can_create_for(request.user),
    )
    if request.method == "POST" and form.is_valid():
        event = form.save(commit=False)
        event.updated_by = request.user
        event.save()
        get_or_create_event_channel(event, actor=request.user)
        messages.success(request, "Event updated successfully.")
        log_audit(
            action_type=AuditLogEntry.ActionType.EVENT_UPDATED,
            acting_user=request.user,
            event=event,
        )
        return redirect("clubs_events:event_detail", pk=event.pk)
    return render(request, "clubs_events/event_form.html", {"form": form, "mode": "Edit"})


@login_required
def event_cancel_view(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if not can_manage_event(request.user, event):
        raise Http404
    form = EventCancellationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        event.status = Event.Status.CANCELLED
        event.cancellation_reason = form.cleaned_data["reason"]
        event.updated_by = request.user
        event.save()
        messages.warning(request, "Event cancelled.")
        return redirect("clubs_events:event_detail", pk=event.pk)
    return render(request, "clubs_events/event_cancel.html", {"event": event, "form": form})


@login_required
def event_register_view(request, pk):
    event = get_object_or_404(Event, pk=pk)
    try:
        event.register_user(request.user)
        messages.success(request, f"You have successfully registered for {event.title}.")
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    return redirect("clubs_events:event_detail", pk=event.pk)


@login_required
def event_cancel_registration_view(request, pk):
    event = get_object_or_404(Event, pk=pk)
    try:
        event.cancel_registration_for_user(request.user)
        messages.info(request, f"Your registration for {event.title} has been cancelled.")
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    return redirect("clubs_events:event_detail", pk=event.pk)


@login_required
def attendance_manage_view(request, pk):
    event = get_object_or_404(Event.objects.select_related("club"), pk=pk)
    if not can_manage_event(request.user, event):
        raise Http404
    registrations = event.registrations.select_related("user").exclude(
        status=Registration.Status.CANCELLED
    )
    if request.method == "POST":
        with transaction.atomic():
            for registration in registrations:
                value = request.POST.get(f"attendance_{registration.pk}")
                if value in Registration.Attendance.values:
                    registration.attendance = value
                    registration.save(update_fields=["attendance", "updated_at"])
        messages.success(request, "Attendance updated.")
        return redirect("clubs_events:attendance_manage", pk=event.pk)
    return render(
        request,
        "clubs_events/attendance_manage.html",
        {
            "event": event,
            "registrations": registrations,
            "attendance_choices": Registration.Attendance.choices,
        },
    )


@login_required
def analytics_dashboard_view(request):
    if is_global_admin(request.user):
        events = Event.objects.select_related("club").all()
    else:
        events = Event.objects.select_related("club").filter(
            club__memberships__user=request.user,
            club__memberships__status=ClubMembership.Status.ACTIVE,
            club__memberships__local_role=ClubMembership.LocalRole.COORDINATOR,
        )
    events = events.prefetch_related(
        Prefetch("registrations", queryset=Registration.objects.select_related("user"))
    )
    return render(request, "clubs_events/analytics_dashboard.html", {"events": events})


@login_required
def announcement_create_view(request, target_type, pk):
    club = event = room = None
    if target_type == "club":
        club = get_object_or_404(Club, pk=pk)
        if not can_post_announcement(request.user, club=club):
            return HttpResponseForbidden("Not allowed")
        redirect_url = reverse("clubs_events:club_detail", args=[club.pk])
    elif target_type == "event":
        event = get_object_or_404(Event.objects.select_related("club"), pk=pk)
        if not can_post_announcement(request.user, event=event):
            return HttpResponseForbidden("Not allowed")
        redirect_url = reverse("clubs_events:event_detail", args=[event.pk])
    elif target_type == "room":
        room = get_object_or_404(DiscussionRoom.objects.select_related("club", "event__club"), pk=pk)
        if not can_post_announcement(request.user, room=room):
            return HttpResponseForbidden("Not allowed")
        redirect_url = reverse("rooms:room_detail", args=[room.pk])
    else:
        raise Http404

    announcement = Announcement(
        target_type=target_type,
        club=club,
        event=event,
        room=room,
    )
    form = AnnouncementForm(request.POST or None, instance=announcement)
    if request.method == "POST" and form.is_valid():
        ann = form.save(commit=False)
        ann.author = request.user
        ann.save()
        action_url = f"{redirect_url}#announcement-{ann.pk}"
        if club:
            recipients = [
                item.user
                for item in club.memberships.filter(status=ClubMembership.Status.ACTIVE).select_related("user")
            ]
        elif event:
            recipients = [
                item.user
                for item in event.registrations.filter(status=Registration.Status.REGISTERED).select_related("user")
            ]
        else:
            recipients = [
                item.user
                for item in room.room_handles.filter(status=RoomHandle.Status.APPROVED).select_related("user")
            ]

        for user in recipients:
            create_notification(
                user=user,
                text=ann.title,
                body=ann.body,
                action_url=action_url,
                notification_type=Notification.Type.ANNOUNCEMENT,
                club=club or (event.club if event else room.club or (room.event.club if room.event else None)),
                event=event,
                room=room,
            )
        log_audit(
            action_type=AuditLogEntry.ActionType.ANNOUNCEMENT_CREATED,
            acting_user=request.user,
            event=event,
            room=room,
            details={
                "club": str(club.id) if club else str(event.club.id) if event else str(room.club_id or room.event.club_id),
                "announcement": str(ann.id),
                "target_type": target_type,
            },
        )
        messages.success(request, "Announcement published.")
        return redirect(action_url)

    return render(
        request,
        "clubs_events/announcement_form.html",
        {
            "form": form,
            "target_type": target_type,
            "club": club,
            "event": event,
            "room": room,
        },
    )
