from __future__ import annotations

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from core.models import AuditLogEntry, Notification
from core.permissions import can_create_room, can_manage_room, can_view_reports, is_global_admin
from core.services import create_notification, log_audit

from .forms import (
    DiscussionRoomForm,
    JoinRoomForm,
    MessageEditForm,
    MessageForm,
    ModerateReportForm,
    ReportForm,
    RoomInviteForm,
)
from .models import DiscussionRoom, Message, Report, RoomHandle, RoomInvite


@login_required
def room_list_view(request):
    rooms = DiscussionRoom.objects.filter(is_archived=False)
    return render(request, "rooms/room_list.html", {"rooms": rooms, "my_handles": request.user.room_handles.select_related("room")})


@login_required
def room_create_view(request):
    form = DiscussionRoomForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        club = form.cleaned_data.get("club")
        event = form.cleaned_data.get("event")
        if not can_create_room(request.user, club=club, event=event):
            return HttpResponseForbidden("You do not have permission to create rooms.")
        room = form.save(commit=False)
        room.created_by = request.user
        room.save()
        log_audit(action_type=AuditLogEntry.ActionType.ROOM_CREATED, acting_user=request.user, room=room)
        return redirect("rooms:room_detail", pk=room.pk)
    return render(request, "rooms/room_form.html", {"form": form, "mode": "Create"})


@login_required
def room_edit_view(request, pk):
    room = get_object_or_404(DiscussionRoom, pk=pk)
    if not can_manage_room(request.user, room):
        raise Http404
    form = DiscussionRoomForm(request.POST or None, instance=room)
    if request.method == "POST" and form.is_valid():
        room = form.save()
        log_audit(action_type=AuditLogEntry.ActionType.ROOM_UPDATED, acting_user=request.user, room=room)
        return redirect("rooms:room_detail", pk=room.pk)
    return render(request, "rooms/room_form.html", {"form": form, "mode": "Edit", "room": room})


def _invite_allows_join(room, user):
    if room.access_type != DiscussionRoom.AccessType.PRIVATE_INVITE_ONLY:
        return True
    return RoomInvite.objects.filter(room=room, recipient=user, status=RoomInvite.Status.ACCEPTED).exists()


@login_required
def join_room_view(request, pk):
    room = get_object_or_404(DiscussionRoom, pk=pk, is_archived=False)
    if request.user.is_globally_banned:
        return redirect("rooms:room_list")
    if not _invite_allows_join(room, request.user):
        return HttpResponseForbidden("Invite required for this room.")

    existing = RoomHandle.objects.filter(room=room, user=request.user).first()
    if existing:
        if existing.status == RoomHandle.Status.EXPELLED:
            return redirect("rooms:room_list")
        if existing.status == RoomHandle.Status.PENDING:
            return redirect("rooms:room_list")
        return redirect("rooms:room_detail", pk=room.pk)

    form = JoinRoomForm(request.POST or None, room=room)
    if request.method == "POST" and form.is_valid():
        status = RoomHandle.Status.APPROVED
        if room.access_type in {DiscussionRoom.AccessType.CLUB_ONLY, DiscussionRoom.AccessType.EVENT_ONLY}:
            status = RoomHandle.Status.PENDING
        RoomHandle.objects.create(
            room=room,
            user=request.user,
            handle_name=form.cleaned_data["handle_name"],
            status=status,
            approved_at=timezone.now() if status == RoomHandle.Status.APPROVED else None,
        )
        return redirect("rooms:room_detail", pk=room.pk) if status == RoomHandle.Status.APPROVED else redirect("rooms:room_list")
    return render(request, "rooms/join_room.html", {"room": room, "form": form})


@login_required
def room_detail_view(request, pk):
    room = get_object_or_404(DiscussionRoom.objects.select_related("club", "event"), pk=pk)
    handle = RoomHandle.objects.filter(room=room, user=request.user).first()
    if not handle:
        return redirect("rooms:join_room", pk=room.pk)
    if handle.status == RoomHandle.Status.PENDING:
        return render(request, "rooms/room_pending.html", {"room": room, "handle": handle})
    if handle.status == RoomHandle.Status.EXPELLED:
        return redirect("rooms:room_list")

    form = MessageForm(request.POST or None)
    if request.method == "POST" and form.is_valid() and not handle.is_muted:
        Message.objects.create(room=room, handle=handle, text=form.cleaned_data["text"])
        return redirect("rooms:room_detail", pk=room.pk)

    return render(
        request,
        "rooms/room_detail.html",
        {
            "room": room,
            "handle": handle,
            "messages_qs": room.messages.select_related("handle", "handle__user"),
            "form": form,
            "pending_handles": room.room_handles.filter(status=RoomHandle.Status.PENDING) if can_manage_room(request.user, room) else None,
            "can_manage_room": can_manage_room(request.user, room),
            "invites": room.invites.select_related("recipient") if can_manage_room(request.user, room) else None,
            "invite_form": RoomInviteForm(room=room),
        },
    )


@login_required
def invite_user_view(request, pk):
    room = get_object_or_404(DiscussionRoom, pk=pk)
    if not can_manage_room(request.user, room):
        return HttpResponseForbidden("Not allowed")
    form = RoomInviteForm(request.POST or None, room=room)
    if request.method == "POST" and form.is_valid():
        invite, _ = RoomInvite.objects.update_or_create(
            room=room,
            recipient=form.cleaned_data["recipient"],
            defaults={"status": RoomInvite.Status.PENDING, "invited_by": request.user},
        )
        create_notification(user=invite.recipient, text=f"You were invited to {room.name}", notification_type=Notification.Type.INVITE, room=room)
        log_audit(action_type=AuditLogEntry.ActionType.ROOM_INVITE_CREATED, acting_user=request.user, room=room, target_user=invite.recipient)
    return redirect("rooms:room_detail", pk=room.pk)


@login_required
def respond_invite_view(request, invite_pk, decision):
    invite = get_object_or_404(RoomInvite, pk=invite_pk, recipient=request.user)
    if invite.status != RoomInvite.Status.PENDING:
        return redirect("core:notifications")
    invite.status = RoomInvite.Status.ACCEPTED if decision == "accept" else RoomInvite.Status.REJECTED
    invite.save(update_fields=["status", "updated_at"])
    log_audit(action_type=AuditLogEntry.ActionType.ROOM_INVITE_UPDATED, acting_user=request.user, room=invite.room, details={"status": invite.status})
    return redirect("rooms:join_room", pk=invite.room_id) if decision == "accept" else redirect("core:notifications")


@login_required
def approve_handle_view(request, room_pk, handle_pk):
    room = get_object_or_404(DiscussionRoom, pk=room_pk)
    if not can_manage_room(request.user, room):
        raise Http404
    handle = get_object_or_404(RoomHandle, pk=handle_pk, room=room)
    handle.status = RoomHandle.Status.APPROVED
    handle.approved_at = timezone.now()
    handle.save(update_fields=["status", "approved_at"])
    return redirect("rooms:room_detail", pk=room.pk)


@login_required
def reject_handle_view(request, room_pk, handle_pk):
    room = get_object_or_404(DiscussionRoom, pk=room_pk)
    if not can_manage_room(request.user, room):
        raise Http404
    handle = get_object_or_404(RoomHandle, pk=handle_pk, room=room)
    handle.delete()
    return redirect("rooms:room_detail", pk=room.pk)


@login_required
def message_edit_view(request, room_pk, message_pk):
    room = get_object_or_404(DiscussionRoom, pk=room_pk)
    message_obj = get_object_or_404(Message, pk=message_pk, room=room)
    if not message_obj.can_be_edited_by(request.user):
        return redirect("rooms:room_detail", pk=room.pk)
    form = MessageEditForm(request.POST or None, initial={"text": message_obj.text})
    if request.method == "POST" and form.is_valid():
        message_obj.text = form.cleaned_data["text"]
        message_obj.is_edited = True
        message_obj.save(update_fields=["text", "is_edited", "updated_at"])
        return redirect("rooms:room_detail", pk=room.pk)
    return render(request, "rooms/message_edit.html", {"room": room, "message_obj": message_obj, "form": form})


@login_required
def message_delete_view(request, room_pk, message_pk):
    room = get_object_or_404(DiscussionRoom, pk=room_pk)
    message_obj = get_object_or_404(Message, pk=message_pk, room=room)
    if message_obj.can_be_edited_by(request.user) or can_manage_room(request.user, room):
        message_obj.soft_delete(actor=request.user)
    return redirect("rooms:room_detail", pk=room.pk)


@login_required
def report_message_view(request, room_pk, message_pk):
    room = get_object_or_404(DiscussionRoom, pk=room_pk)
    message_obj = get_object_or_404(Message, pk=message_pk, room=room)
    form = ReportForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        Report.objects.create(message=message_obj, reporter=request.user, reason=form.cleaned_data["reason"])
        return redirect("rooms:room_detail", pk=room.pk)
    return render(request, "rooms/report_form.html", {"room": room, "message_obj": message_obj, "form": form})


@login_required
def moderation_dashboard_view(request):
    if not can_view_reports(request.user):
        return HttpResponseForbidden("Only institute and system admins can access this page.")
    reports = Report.objects.select_related("message", "message__room", "message__handle", "reporter")
    status = request.GET.get("status")
    if status:
        reports = reports.filter(status=status)
    return render(request, "rooms/moderation_dashboard.html", {"reports": reports, "status": status, "rooms": DiscussionRoom.objects.all(), "status_choices": Report.Status.choices})


@login_required
def moderate_report_view(request, report_pk):
    if not can_view_reports(request.user):
        return HttpResponseForbidden("Only institute and system admins can access this page.")
    report = get_object_or_404(Report.objects.select_related("message", "message__room", "message__handle", "message__handle__user", "reporter"), pk=report_pk)
    room = report.message.room
    surrounding_messages = room.messages.filter(created_at__gte=report.message.created_at - timedelta(minutes=10), created_at__lte=report.message.created_at + timedelta(minutes=10)).select_related("handle")

    form = ModerateReportForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        action = form.cleaned_data["action"]
        report.status = Report.Status.DISMISSED if action == ModerateReportForm.ACTION_DISMISS else Report.Status.ACTION_TAKEN
        report.resolved_by = request.user
        report.resolution_reason = form.cleaned_data["reason"]
        report.resolved_at = timezone.now()
        report.save(update_fields=["status", "resolved_by", "resolution_reason", "resolved_at", "updated_at"])
    return render(request, "rooms/moderate_report.html", {"report": report, "room": room, "form": form, "surrounding_messages": surrounding_messages})
