from __future__ import annotations

from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import models
from django.db.models import OuterRef, Subquery
from django.http import HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.formats import date_format
from django.template.defaultfilters import linebreaksbr
from django.utils.html import escape

from clubs_events.models import Club, Event
from rooms.models import DiscussionRoom

from .forms import DirectMessageForm, DirectMessageStartForm, SearchForm
from .models import (
    DirectMessageBlock,
    DirectMessage,
    DirectMessageParticipant,
    DirectMessageThread,
    Notification,
)


def root_redirect(request):
    if request.user.is_authenticated:
        return redirect("clubs_events:event_feed")
    return redirect("accounts:login")


def web_manifest_view(request):
    response = JsonResponse(
        {
            "name": "ClubsHub",
            "short_name": "ClubsHub",
            "description": "Clubs, events, rooms, notifications, and inbox for IIT Kanpur communities.",
            "id": "/",
            "start_url": reverse("core:root"),
            "scope": "/",
            "display": "standalone",
            "background_color": "#08111f",
            "theme_color": "#0b1324",
            "orientation": "portrait",
            "icons": [
                {
                    "src": static("icons/icon-192.png"),
                    "sizes": "192x192",
                    "type": "image/png",
                    "purpose": "any",
                },
                {
                    "src": static("icons/icon-512.png"),
                    "sizes": "512x512",
                    "type": "image/png",
                    "purpose": "any",
                },
                {
                    "src": static("icons/icon-maskable-512.png"),
                    "sizes": "512x512",
                    "type": "image/png",
                    "purpose": "maskable",
                },
            ],
        }
    )
    response["Content-Type"] = "application/manifest+json"
    response["Cache-Control"] = "no-cache"
    return response


def service_worker_view(request):
    response = render(request, "core/service_worker.js", content_type="application/javascript")
    response["Cache-Control"] = "no-cache"
    return response


def offline_view(request):
    return render(request, "core/offline.html")


@login_required
def notifications_list_view(request):
    notifications = request.user.notifications.select_related(
        "club", "event", "room", "message"
    ).all()
    if request.method == "POST":
        notifications.filter(is_read=False).update(is_read=True)
        return redirect("core:notifications")
    return render(
        request,
        "core/notifications_list.html",
        {"notifications": notifications},
    )


@login_required
def mark_notification_read_view(request, pk):
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    notification.is_read = True
    notification.save(update_fields=["is_read"])
    return redirect("core:notifications")


@login_required
def open_notification_view(request, pk):
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    if not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=["is_read"])

    if notification.action_url:
        return redirect(notification.action_url)
    if notification.message_id and notification.room_id:
        params = urlencode({"focus": str(notification.message_id), "source": "notification"})
        return redirect(f"{reverse('rooms:room_detail', args=[notification.room_id])}?{params}")
    if notification.room_id:
        return redirect("rooms:room_detail", pk=notification.room_id)
    if notification.event_id:
        return redirect("clubs_events:event_detail", pk=notification.event_id)
    if notification.club_id:
        return redirect("clubs_events:club_detail", pk=notification.club_id)
    return redirect("core:notifications")


@login_required
def notifications_feed_view(request):
    notifications = (
        request.user.notifications.select_related("club", "event", "room", "message")
        .filter(is_read=False)[:10]
    )
    items = []
    for notification in notifications:
        if notification.action_url:
            url = notification.action_url
        elif notification.message_id and notification.room_id:
            params = urlencode({"focus": str(notification.message_id), "source": "notification"})
            url = f"{reverse('rooms:room_detail', args=[notification.room_id])}?{params}"
        elif notification.room_id:
            url = reverse("rooms:room_detail", args=[notification.room_id])
        elif notification.event_id:
            url = reverse("clubs_events:event_detail", args=[notification.event_id])
        elif notification.club_id:
            url = reverse("clubs_events:club_detail", args=[notification.club_id])
        else:
            url = reverse("core:notifications")
        items.append(
            {
                "id": str(notification.pk),
                "title": notification.text,
                "body": notification.body,
                "type": notification.notification_type,
                "url": url,
                "created_at": notification.created_at.isoformat(),
            }
        )
    return JsonResponse(
        {
            "unread_count": request.user.notifications.filter(is_read=False).count(),
            "items": items,
        }
    )


def _get_dm_threads(user):
    last_message = DirectMessage.objects.filter(thread=OuterRef("pk")).order_by(
        "-created_at"
    )
    threads = (
        DirectMessageThread.objects.filter(participants=user)
        .distinct()
        .annotate(
            last_message_at=Subquery(last_message.values("created_at")[:1]),
            last_message_body=Subquery(last_message.values("body")[:1]),
        )
        .prefetch_related("participants_meta__user")
    )
    for thread in threads:
        participants = list(thread.participants_meta.all())
        me = next((p for p in participants if p.user_id == user.id), None)
        other = next((p for p in participants if p.user_id != user.id), None)
        thread.me_participant = me
        thread.other_user = other.user if other else None
        last_read = me.last_read_at if me else None
        thread.is_unread = bool(
            thread.last_message_at and (not last_read or thread.last_message_at > last_read)
        )
    return threads


def _get_or_create_dm_thread(user, recipient):
    thread = (
        DirectMessageThread.objects.filter(participants=user)
        .filter(participants=recipient)
        .distinct()
        .first()
    )
    if thread:
        return thread
    thread = DirectMessageThread.objects.create()
    DirectMessageParticipant.objects.create(
        thread=thread, user=user, last_read_at=timezone.now()
    )
    DirectMessageParticipant.objects.create(thread=thread, user=recipient)
    return thread


def _get_dm_block_state(user, other_user):
    blocked_by_me = DirectMessageBlock.objects.filter(
        blocker=user, blocked=other_user
    ).exists()
    blocked_me = DirectMessageBlock.objects.filter(
        blocker=other_user, blocked=user
    ).exists()
    return blocked_by_me, blocked_me


def _serialize_dm_message(message, viewer):
    created_at = timezone.localtime(message.created_at)
    return {
        "id": str(message.id),
        "body_html": str(linebreaksbr(escape(message.body))),
        "created_at": message.created_at.isoformat(),
        "created_at_display": date_format(created_at, "DATETIME_FORMAT"),
        "sender_name": message.sender.display_name,
        "is_me": message.sender_id == viewer.id,
    }


@login_required
def inbox_view(request):
    start_form = DirectMessageStartForm(request.POST or None, user=request.user)
    if request.method == "POST" and start_form.is_valid():
        thread = _get_or_create_dm_thread(
            request.user, start_form.cleaned_data["recipient"]
        )
        return redirect("core:inbox_thread", thread_pk=thread.pk)
    threads = _get_dm_threads(request.user)
    return render(
        request,
        "core/inbox.html",
        {
            "threads": threads,
            "start_form": start_form,
            "active_thread": None,
            "message_form": None,
            "dm_messages": [],
            "can_send": False,
            "blocked_by_me": False,
            "blocked_me": False,
        },
    )


@login_required
def inbox_thread_view(request, thread_pk):
    thread = get_object_or_404(
        DirectMessageThread.objects.filter(participants=request.user),
        pk=thread_pk,
    )
    participant = DirectMessageParticipant.objects.filter(
        thread=thread, user=request.user
    ).first()
    message_form = DirectMessageForm(request.POST or None)
    other_user = thread.participants.exclude(id=request.user.id).first()
    blocked_by_me = False
    blocked_me = False
    can_send = True
    if other_user:
        blocked_by_me, blocked_me = _get_dm_block_state(request.user, other_user)
        can_send = not (blocked_by_me or blocked_me)

    if request.method == "POST":
        if not can_send:
            messages.error(request, "You cannot send messages in this chat.")
            return redirect("core:inbox_thread", thread_pk=thread.pk)
        if message_form.is_valid():
            DirectMessage.objects.create(
                thread=thread,
                sender=request.user,
                body=message_form.cleaned_data["body"],
            )
            if participant:
                participant.last_read_at = timezone.now()
                participant.save(update_fields=["last_read_at"])
            thread.touch()
            return redirect("core:inbox_thread", thread_pk=thread.pk)

    if participant:
        participant.last_read_at = timezone.now()
        participant.save(update_fields=["last_read_at"])

    messages_qs = thread.messages.select_related("sender")
    last_message = messages_qs.last()
    threads = _get_dm_threads(request.user)
    start_form = DirectMessageStartForm(user=request.user)

    return render(
        request,
        "core/inbox.html",
        {
            "threads": threads,
            "start_form": start_form,
            "active_thread": thread,
            "message_form": message_form,
            "dm_messages": messages_qs,
            "other_user": other_user,
            "can_send": can_send,
            "blocked_by_me": blocked_by_me,
            "blocked_me": blocked_me,
            "last_message_at": last_message.created_at if last_message else None,
        },
    )


@login_required
def inbox_block_view(request, thread_pk, action):
    if request.method != "POST":
        return redirect("core:inbox_thread", thread_pk=thread_pk)
    thread = get_object_or_404(
        DirectMessageThread.objects.filter(participants=request.user),
        pk=thread_pk,
    )
    other_user = thread.participants.exclude(id=request.user.id).first()
    if not other_user:
        return redirect("core:inbox_thread", thread_pk=thread_pk)
    if action == "block":
        DirectMessageBlock.objects.get_or_create(
            blocker=request.user, blocked=other_user
        )
        messages.success(request, f"You blocked {other_user.display_name}.")
    elif action == "unblock":
        DirectMessageBlock.objects.filter(
            blocker=request.user, blocked=other_user
        ).delete()
        messages.success(request, f"You unblocked {other_user.display_name}.")
    return redirect("core:inbox_thread", thread_pk=thread_pk)


@login_required
def inbox_messages_view(request, thread_pk):
    thread = get_object_or_404(
        DirectMessageThread.objects.filter(participants=request.user),
        pk=thread_pk,
    )
    since = request.GET.get("since", "").strip()
    messages_qs = thread.messages.select_related("sender")
    if since:
        parsed = parse_datetime(since)
        if parsed:
            if timezone.is_naive(parsed):
                parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
            messages_qs = messages_qs.filter(created_at__gt=parsed)
    items = [_serialize_dm_message(message, request.user) for message in messages_qs]
    if items:
        participant = DirectMessageParticipant.objects.filter(
            thread=thread, user=request.user
        ).first()
        if participant:
            participant.last_read_at = timezone.now()
            participant.save(update_fields=["last_read_at"])
    return JsonResponse({"items": items})


@login_required
def inbox_send_view(request, thread_pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    thread = get_object_or_404(
        DirectMessageThread.objects.filter(participants=request.user),
        pk=thread_pk,
    )
    other_user = thread.participants.exclude(id=request.user.id).first()
    if other_user:
        blocked_by_me, blocked_me = _get_dm_block_state(request.user, other_user)
        if blocked_by_me or blocked_me:
            return JsonResponse({"error": "blocked"}, status=403)
    form = DirectMessageForm(request.POST)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors}, status=400)
    message = DirectMessage.objects.create(
        thread=thread,
        sender=request.user,
        body=form.cleaned_data["body"],
    )
    participant = DirectMessageParticipant.objects.filter(
        thread=thread, user=request.user
    ).first()
    if participant:
        participant.last_read_at = timezone.now()
        participant.save(update_fields=["last_read_at"])
    thread.touch()
    return JsonResponse({"item": _serialize_dm_message(message, request.user)})


@login_required
def search_view(request):
    form = SearchForm(request.GET or None)
    query = ""
    clubs = Club.objects.none()
    events = Event.objects.none()
    rooms = DiscussionRoom.objects.none()
    if form.is_valid():
        query = form.cleaned_data["q"].strip()
        if query:
            clubs = Club.objects.filter(is_active=True).filter(
                models.Q(name__icontains=query)
                | models.Q(description__icontains=query)
                | models.Q(category__icontains=query)
            )
            events = Event.objects.filter(status=Event.Status.PUBLISHED).filter(
                models.Q(title__icontains=query)
                | models.Q(description__icontains=query)
                | models.Q(tags__icontains=query)
                | models.Q(club__name__icontains=query)
            )
            rooms = DiscussionRoom.objects.filter(
                is_archived=False, room_type=DiscussionRoom.RoomType.TOPIC
            ).filter(
                models.Q(name__icontains=query) | models.Q(description__icontains=query)
            )

    return render(
        request,
        "core/search_results.html",
        {
            "form": form,
            "query": query,
            "clubs": clubs,
            "events": events,
            "rooms": rooms,
        },
    )


@login_required
def user_search_view(request):
    query = request.GET.get("q", "").strip()
    items = []
    if len(query) >= 2:
        User = get_user_model()
        qs = User.objects.filter(is_active=True).exclude(id=request.user.id)
        qs = qs.filter(
            models.Q(username__icontains=query)
            | models.Q(email__icontains=query)
            | models.Q(first_name__icontains=query)
            | models.Q(last_name__icontains=query)
        ).order_by("username")[:8]
        items = [
            {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "display_name": user.display_name,
                "label": f"{user.username} ({user.display_name})",
            }
            for user in qs
        ]
    return JsonResponse({"items": items})


def help_view(request):
    return render(request, "core/help.html")
