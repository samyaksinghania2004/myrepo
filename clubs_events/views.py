from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Prefetch, Q
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.models import User
from core.models import Notification
from core.services import log_audit

from .forms import ClubForm, EventCancellationForm, EventForm
from .models import Club, ClubFollow, Event, Registration


def _club_queryset_for_user(user):
    if user.role in {User.Role.INSTITUTE_ADMIN, User.Role.SYSTEM_ADMIN}:
        return Club.objects.filter(is_active=True)
    if user.role == User.Role.CLUB_REP:
        return user.represented_clubs.filter(is_active=True)
    return Club.objects.none()


def _ensure_event_manager(user, event: Event):
    if not event.can_be_managed_by(user):
        raise Http404


def _ensure_club_admin(user):
    if user.role not in {User.Role.INSTITUTE_ADMIN, User.Role.SYSTEM_ADMIN}:
        return HttpResponseForbidden("Only institute or system admins can manage clubs.")
    return None


@login_required
def event_feed_view(request):
    Event.objects.filter(status=Event.Status.PUBLISHED, end_time__lt=timezone.now()).update(
        status=Event.Status.COMPLETED
    )

    q = request.GET.get("q", "").strip()[:50]
    club_id = request.GET.get("club", "").strip()
    tag = request.GET.get("tag", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()

    events = Event.objects.select_related("club").filter(
        status=Event.Status.PUBLISHED, start_time__gte=timezone.now()
    )
    if q:
        events = events.filter(
            Q(title__icontains=q)
            | Q(description__icontains=q)
            | Q(tags__icontains=q)
            | Q(club__name__icontains=q)
        )
    if club_id:
        events = events.filter(club_id=club_id)
    if tag:
        events = events.filter(tags__icontains=tag)
    if date_from:
        events = events.filter(start_time__date__gte=date_from)
    if date_to:
        events = events.filter(start_time__date__lte=date_to)

    my_registrations = request.user.registrations.select_related("event", "event__club").filter(
        event__start_time__gte=timezone.now(),
        status__in=[Registration.Status.REGISTERED, Registration.Status.WAITLISTED],
    )
    followed_club_ids = request.user.followed_clubs.values_list("id", flat=True)
    followed_events = Event.objects.select_related("club").filter(
        club_id__in=followed_club_ids,
        status=Event.Status.PUBLISHED,
        start_time__gte=timezone.now(),
    )[:5]

    context = {
        "events": events,
        "clubs": Club.objects.filter(is_active=True),
        "q": q,
        "selected_club": club_id,
        "tag": tag,
        "date_from": date_from,
        "date_to": date_to,
        "my_registrations": my_registrations,
        "followed_events": followed_events,
    }
    return render(request, "clubs_events/event_feed.html", context)


@login_required
def club_list_view(request):
    q = request.GET.get("q", "").strip()[:50]
    clubs = Club.objects.filter(is_active=True)
    if q:
        clubs = clubs.filter(
            Q(name__icontains=q) | Q(category__icontains=q) | Q(description__icontains=q)
        )
    user_followed_ids = set(request.user.followed_clubs.values_list("id", flat=True))
    return render(
        request,
        "clubs_events/club_list.html",
        {"clubs": clubs, "q": q, "user_followed_ids": user_followed_ids},
    )


@login_required
def club_detail_view(request, pk):
    club = get_object_or_404(
        Club.objects.prefetch_related("representatives", "events", "followers"), pk=pk
    )
    upcoming_events = club.events.filter(start_time__gte=timezone.now()).exclude(
        status=Event.Status.CANCELLED
    )
    is_following = club.followers.filter(pk=request.user.pk).exists()
    followers = club.followers.all() if club.can_be_managed_by(request.user) else []
    return render(
        request,
        "clubs_events/club_detail.html",
        {
            "club": club,
            "upcoming_events": upcoming_events,
            "is_following": is_following,
            "followers": followers,
        },
    )


@login_required
def club_follow_toggle_view(request, pk):
    club = get_object_or_404(Club, pk=pk, is_active=True)
    follow = ClubFollow.objects.filter(club=club, user=request.user).first()
    if follow:
        follow.delete()
        messages.info(request, f"You unfollowed {club.name}.")
    else:
        ClubFollow.objects.create(club=club, user=request.user)
        messages.success(request, f"You are now following {club.name}.")
    next_url = request.POST.get("next")
    if next_url:
        return redirect(next_url)
    return redirect("clubs_events:club_detail", pk=club.pk)


@login_required
def club_create_view(request):
    forbidden = _ensure_club_admin(request.user)
    if forbidden:
        return forbidden
    if request.method == "POST":
        form = ClubForm(request.POST)
        if form.is_valid():
            club = form.save()
            log_audit(
                action_type="club_created",
                acting_user=request.user,
                reason=f"Club {club.name} created.",
                details={"club": club.name},
            )
            messages.success(request, "Club created successfully.")
            return redirect("clubs_events:club_detail", pk=club.pk)
    else:
        form = ClubForm()
    return render(request, "clubs_events/club_form.html", {"form": form, "mode": "Create"})


@login_required
def club_edit_view(request, pk):
    forbidden = _ensure_club_admin(request.user)
    if forbidden:
        return forbidden
    club = get_object_or_404(Club, pk=pk)
    if request.method == "POST":
        form = ClubForm(request.POST, instance=club)
        if form.is_valid():
            club = form.save()
            log_audit(
                action_type="club_updated",
                acting_user=request.user,
                reason=f"Club {club.name} updated.",
                details={"club": club.name},
            )
            messages.success(request, "Club updated successfully.")
            return redirect("clubs_events:club_detail", pk=club.pk)
    else:
        form = ClubForm(instance=club)
    return render(request, "clubs_events/club_form.html", {"form": form, "mode": "Edit"})


@login_required
def event_detail_view(request, pk):
    event = get_object_or_404(Event.objects.select_related("club"), pk=pk)
    event.refresh_status_from_time()
    registration = request.user.registrations.filter(event=event).first()
    registrations = None
    if event.can_be_managed_by(request.user):
        registrations = event.registrations.select_related("user")
    return render(
        request,
        "clubs_events/event_detail.html",
        {
            "event": event,
            "registration": registration,
            "registrations": registrations,
            "can_manage_event": event.can_be_managed_by(request.user),
        },
    )


@login_required
def my_events_view(request):
    registrations = request.user.registrations.select_related("event", "event__club").all()
    return render(request, "clubs_events/my_events.html", {"registrations": registrations})


@login_required
def event_create_view(request):
    available_clubs = _club_queryset_for_user(request.user)
    if not available_clubs.exists():
        return HttpResponseForbidden("You do not have permission to create events.")
    if request.method == "POST":
        form = EventForm(request.POST, club_queryset=available_clubs)
        if form.is_valid():
            event = form.save(commit=False)
            event.created_by = request.user
            event.updated_by = request.user
            event.save()
            log_audit(
                action_type="event_created",
                acting_user=request.user,
                event=event,
                reason=f"Event {event.title} created.",
            )
            messages.success(request, "Event created successfully.")
            return redirect("clubs_events:event_detail", pk=event.pk)
    else:
        initial_club = available_clubs.first() if available_clubs.count() == 1 else None
        form = EventForm(initial={"club": initial_club}, club_queryset=available_clubs)
    return render(request, "clubs_events/event_form.html", {"form": form, "mode": "Create"})


@login_required
def event_edit_view(request, pk):
    event = get_object_or_404(Event, pk=pk)
    _ensure_event_manager(request.user, event)
    if timezone.now() >= event.start_time:
        messages.error(request, "Started events cannot be edited.")
        return redirect("clubs_events:event_detail", pk=event.pk)
    if request.method == "POST":
        form = EventForm(
            request.POST,
            instance=event,
            club_queryset=_club_queryset_for_user(request.user),
        )
        if form.is_valid():
            event = form.save(commit=False)
            event.updated_by = request.user
            event.save()
            event.notify_registrants(
                text=f"Event details updated for {event.title}.",
                notification_type=Notification.Type.EVENT_UPDATED,
            )
            log_audit(
                action_type="event_updated",
                acting_user=request.user,
                event=event,
                reason=f"Event {event.title} updated.",
            )
            messages.success(request, "Event updated successfully.")
            return redirect("clubs_events:event_detail", pk=event.pk)
    else:
        form = EventForm(instance=event, club_queryset=_club_queryset_for_user(request.user))
    return render(request, "clubs_events/event_form.html", {"form": form, "mode": "Edit"})


@login_required
def event_cancel_view(request, pk):
    event = get_object_or_404(Event, pk=pk)
    _ensure_event_manager(request.user, event)
    if timezone.now() >= event.start_time:
        messages.error(request, "Started events cannot be cancelled.")
        return redirect("clubs_events:event_detail", pk=event.pk)
    if request.method == "POST":
        form = EventCancellationForm(request.POST)
        if form.is_valid():
            event.status = Event.Status.CANCELLED
            event.cancellation_reason = form.cleaned_data["reason"]
            event.updated_by = request.user
            event.save()
            event.notify_registrants(
                text=f"Event cancelled: {event.title}. Reason: {event.cancellation_reason}",
                notification_type=Notification.Type.EVENT_CANCELLED,
            )
            log_audit(
                action_type="event_cancelled",
                acting_user=request.user,
                event=event,
                reason=event.cancellation_reason,
            )
            messages.success(request, "Event cancelled.")
            return redirect("clubs_events:event_detail", pk=event.pk)
    else:
        form = EventCancellationForm()
    return render(
        request,
        "clubs_events/event_cancel.html",
        {"event": event, "form": form},
    )


@login_required
def event_register_view(request, pk):
    event = get_object_or_404(Event, pk=pk)
    try:
        event.register_user(request.user)
        messages.success(request, "Registration updated successfully.")
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    return redirect("clubs_events:event_detail", pk=event.pk)


@login_required
def event_cancel_registration_view(request, pk):
    event = get_object_or_404(Event, pk=pk)
    try:
        event.cancel_registration_for_user(request.user)
        messages.info(request, "Registration cancelled.")
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    return redirect("clubs_events:event_detail", pk=event.pk)


@login_required
def attendance_manage_view(request, pk):
    event = get_object_or_404(Event.objects.select_related("club"), pk=pk)
    _ensure_event_manager(request.user, event)
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
    if request.user.role in {User.Role.INSTITUTE_ADMIN, User.Role.SYSTEM_ADMIN}:
        events = Event.objects.select_related("club").all()
    elif request.user.role == User.Role.CLUB_REP:
        events = Event.objects.select_related("club").filter(club__representatives=request.user)
    else:
        return HttpResponseForbidden("Only club representatives and admins can view analytics.")

    events = events.prefetch_related(
        Prefetch("registrations", queryset=Registration.objects.select_related("user"))
    )
    return render(request, "clubs_events/analytics_dashboard.html", {"events": events})
