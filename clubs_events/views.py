from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Prefetch, Q
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from core.models import AuditLogEntry, Notification
from core.permissions import (
    LOCAL_ROLE_COORDINATOR,
    LOCAL_ROLE_MEMBER,
    LOCAL_ROLE_SECRETARY,
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

from .forms import AnnouncementForm, ClubForm, EventCancellationForm, EventForm
from .models import Announcement, Club, ClubMembership, Event, Registration


def _clubs_user_can_create_for(user):
    if is_global_admin(user):
        return Club.objects.filter(is_active=True)
    return Club.objects.filter(
        memberships__user=user,
        memberships__status=ClubMembership.Status.ACTIVE,
        memberships__local_role__in=[ClubMembership.LocalRole.COORDINATOR, ClubMembership.LocalRole.SECRETARY],
        is_active=True,
    )


@login_required
def event_feed_view(request):
    Event.objects.filter(status=Event.Status.PUBLISHED, end_time__lt=timezone.now()).update(
        status=Event.Status.COMPLETED
    )
    q = request.GET.get("q", "").strip()[:50]
    events = Event.objects.select_related("club").filter(
        status=Event.Status.PUBLISHED, start_time__gte=timezone.now(), is_archived=False
    )
    if q:
        events = events.filter(Q(title__icontains=q) | Q(description__icontains=q))
    return render(request, "clubs_events/event_feed.html", {"events": events, "q": q})


@login_required
def club_list_view(request):
    q = request.GET.get("q", "").strip()[:50]
    clubs = Club.objects.filter(is_active=True)
    if q:
        clubs = clubs.filter(Q(name__icontains=q) | Q(category__icontains=q))
    active_memberships = set(
        request.user.club_memberships.filter(status=ClubMembership.Status.ACTIVE).values_list(
            "club_id", flat=True
        )
    )
    return render(
        request,
        "clubs_events/club_list.html",
        {"clubs": clubs, "q": q, "active_membership_ids": active_memberships},
    )


@login_required
def club_detail_view(request, pk):
    club = get_object_or_404(Club, pk=pk)
    membership = ClubMembership.objects.filter(club=club, user=request.user).first()
    announcements = club.announcements.filter(is_active=True)[:10]
    members = club.memberships.filter(status=ClubMembership.Status.ACTIVE).select_related("user")
    return render(
        request,
        "clubs_events/club_detail.html",
        {
            "club": club,
            "membership": membership,
            "members": members,
            "announcements": announcements,
            "can_manage_club": can_manage_club(request.user, club),
            "can_post_announcement": can_post_announcement(request.user, club=club),
        },
    )


@login_required
def club_join_view(request, pk):
    club = get_object_or_404(Club, pk=pk, is_active=True)
    membership, created = ClubMembership.objects.get_or_create(
        club=club,
        user=request.user,
        defaults={"status": ClubMembership.Status.ACTIVE, "local_role": ClubMembership.LocalRole.MEMBER},
    )
    if not created:
        membership.status = ClubMembership.Status.ACTIVE
        membership.local_role = ClubMembership.LocalRole.MEMBER
        membership.left_at = None
        membership.save(update_fields=["status", "local_role", "left_at", "updated_at"])
    log_audit(action_type=AuditLogEntry.ActionType.CLUB_JOINED, acting_user=request.user, details={"club": str(club.id)})
    return redirect("clubs_events:club_detail", pk=club.pk)


@login_required
def club_leave_view(request, pk):
    club = get_object_or_404(Club, pk=pk)
    membership = get_object_or_404(ClubMembership, club=club, user=request.user)
    membership.status = ClubMembership.Status.LEFT
    membership.local_role = ClubMembership.LocalRole.MEMBER
    membership.left_at = timezone.now()
    membership.save(update_fields=["status", "local_role", "left_at", "updated_at"])
    log_audit(action_type=AuditLogEntry.ActionType.CLUB_LEFT, acting_user=request.user, details={"club": str(club.id)})
    return redirect("clubs_events:club_detail", pk=club.pk)


@login_required
def assign_secretary_view(request, pk, user_id):
    club = get_object_or_404(Club, pk=pk)
    target_membership = get_object_or_404(ClubMembership, club=club, user_id=user_id)
    if not can_assign_secretary(request.user, club, target_membership.user):
        return HttpResponseForbidden("Not allowed")
    target_membership.local_role = ClubMembership.LocalRole.SECRETARY
    target_membership.assigned_by = request.user
    target_membership.save(update_fields=["local_role", "assigned_by", "updated_at"])
    log_audit(action_type=AuditLogEntry.ActionType.ROLE_GRANTED, acting_user=request.user, target_user=target_membership.user, details={"role": "secretary", "club": str(club.id)})
    return redirect("clubs_events:club_detail", pk=club.pk)


@login_required
def revoke_secretary_view(request, pk, user_id):
    club = get_object_or_404(Club, pk=pk)
    target_membership = get_object_or_404(ClubMembership, club=club, user_id=user_id)
    if not can_assign_secretary(request.user, club, target_membership.user):
        return HttpResponseForbidden("Not allowed")
    target_membership.local_role = ClubMembership.LocalRole.MEMBER
    target_membership.save(update_fields=["local_role", "updated_at"])
    log_audit(action_type=AuditLogEntry.ActionType.ROLE_REVOKED, acting_user=request.user, target_user=target_membership.user, details={"role": "secretary", "club": str(club.id)})
    return redirect("clubs_events:club_detail", pk=club.pk)


@login_required
def club_create_view(request):
    if not can_create_club(request.user):
        return HttpResponseForbidden("Only institute or system admins can manage clubs.")
    form = ClubForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        club = form.save()
        messages.success(request, "Club created successfully.")
        log_audit(action_type=AuditLogEntry.ActionType.CLUB_CREATED, acting_user=request.user, details={"club": str(club.id)})
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
        log_audit(action_type=AuditLogEntry.ActionType.CLUB_UPDATED, acting_user=request.user, details={"club": str(club.id)})
        return redirect("clubs_events:club_detail", pk=club.pk)
    return render(request, "clubs_events/club_form.html", {"form": form, "mode": "Edit"})


@login_required
def event_detail_view(request, pk):
    event = get_object_or_404(Event.objects.select_related("club"), pk=pk)
    registration = request.user.registrations.filter(event=event).first()
    announcements = event.announcements.filter(is_active=True)[:10]
    return render(request, "clubs_events/event_detail.html", {"event": event, "registration": registration, "can_manage_event": can_manage_event(request.user, event), "announcements": announcements, "can_post_announcement": can_post_announcement(request.user, event=event)})


@login_required
def my_events_view(request):
    registrations = request.user.registrations.select_related("event", "event__club").all()
    return render(request, "clubs_events/my_events.html", {"registrations": registrations})


@login_required
def event_create_view(request):
    available_clubs = _clubs_user_can_create_for(request.user)
    if not available_clubs.exists():
        return HttpResponseForbidden("You do not have permission to create events.")
    form = EventForm(request.POST or None, club_queryset=available_clubs)
    if request.method == "POST" and form.is_valid():
        if not can_create_event(request.user, form.cleaned_data["club"]):
            return HttpResponseForbidden("You do not have permission to create events.")
        event = form.save(commit=False)
        event.created_by = request.user
        event.updated_by = request.user
        event.save()
        log_audit(action_type=AuditLogEntry.ActionType.EVENT_CREATED, acting_user=request.user, event=event)
        return redirect("clubs_events:event_detail", pk=event.pk)
    return render(request, "clubs_events/event_form.html", {"form": form, "mode": "Create"})


@login_required
def event_edit_view(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if not can_manage_event(request.user, event):
        raise Http404
    form = EventForm(request.POST or None, instance=event, club_queryset=_clubs_user_can_create_for(request.user))
    if request.method == "POST" and form.is_valid():
        event = form.save(commit=False)
        event.updated_by = request.user
        event.save()
        log_audit(action_type=AuditLogEntry.ActionType.EVENT_UPDATED, acting_user=request.user, event=event)
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
        return redirect("clubs_events:event_detail", pk=event.pk)
    return render(request, "clubs_events/event_cancel.html", {"event": event, "form": form})


@login_required
def event_register_view(request, pk):
    event = get_object_or_404(Event, pk=pk)
    try:
        event.register_user(request.user)
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    return redirect("clubs_events:event_detail", pk=event.pk)


@login_required
def event_cancel_registration_view(request, pk):
    event = get_object_or_404(Event, pk=pk)
    try:
        event.cancel_registration_for_user(request.user)
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    return redirect("clubs_events:event_detail", pk=event.pk)


@login_required
def attendance_manage_view(request, pk):
    event = get_object_or_404(Event.objects.select_related("club"), pk=pk)
    if not can_manage_event(request.user, event):
        raise Http404
    registrations = event.registrations.select_related("user").exclude(status=Registration.Status.CANCELLED)
    if request.method == "POST":
        with transaction.atomic():
            for registration in registrations:
                value = request.POST.get(f"attendance_{registration.pk}")
                if value in Registration.Attendance.values:
                    registration.attendance = value
                    registration.save(update_fields=["attendance", "updated_at"])
        return redirect("clubs_events:attendance_manage", pk=event.pk)
    return render(request, "clubs_events/attendance_manage.html", {"event": event, "registrations": registrations, "attendance_choices": Registration.Attendance.choices})


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
    events = events.prefetch_related(Prefetch("registrations", queryset=Registration.objects.select_related("user")))
    return render(request, "clubs_events/analytics_dashboard.html", {"events": events})


@login_required
def announcement_create_view(request, target_type, pk):
    club = event = room = None
    if target_type == "club":
        club = get_object_or_404(Club, pk=pk)
        if not can_post_announcement(request.user, club=club):
            return HttpResponseForbidden("Not allowed")
    elif target_type == "event":
        event = get_object_or_404(Event, pk=pk)
        if not can_post_announcement(request.user, event=event):
            return HttpResponseForbidden("Not allowed")
    else:
        raise Http404

    form = AnnouncementForm(request.POST or None)
    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        body = request.POST.get("body", "").strip()
        if title and body:
            ann = Announcement.objects.create(
                author=request.user,
                target_type=target_type,
                club=club,
                event=event,
                title=title,
                body=body,
            )
        else:
            return render(request, "clubs_events/event_form.html", {"form": form, "mode": "Announcement"})
        recipients = []
        if club:
            recipients = [m.user for m in club.memberships.filter(status=ClubMembership.Status.ACTIVE).select_related("user")]
        elif event:
            recipients = [r.user for r in event.registrations.filter(status=Registration.Status.REGISTERED).select_related("user")]
        for user in recipients:
            create_notification(user=user, text=f"Announcement: {ann.title}", notification_type=Notification.Type.ANNOUNCEMENT, event=event)
        log_audit(action_type=AuditLogEntry.ActionType.ANNOUNCEMENT_CREATED, acting_user=request.user, event=event, details={"club": str(club.id) if club else None})
        return redirect("clubs_events:club_detail", pk=club.pk) if club else redirect("clubs_events:event_detail", pk=event.pk)
    return render(request, "clubs_events/event_form.html", {"form": form, "mode": "Announcement"})
