from __future__ import annotations

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.models import User
from core.models import AuditLogEntry, Notification
from core.services import create_notification, log_audit

from .forms import (
    DiscussionRoomForm,
    JoinRoomForm,
    MessageEditForm,
    MessageForm,
    ModerateReportForm,
    ReportForm,
)
from .models import DiscussionRoom, Message, Report, RoomHandle


def _ensure_room_manager(user, room: DiscussionRoom):
    if not room.can_be_managed_by(user):
        raise Http404


def _ensure_moderator(user):
    if user.role not in {User.Role.MODERATOR, User.Role.INSTITUTE_ADMIN, User.Role.SYSTEM_ADMIN}:
        return HttpResponseForbidden("Only moderators and admins can access this page.")
    return None


@login_required
def room_list_view(request):
    q = request.GET.get("q", "").strip()[:50]
    rooms = DiscussionRoom.objects.filter(is_archived=False)
    if q:
        rooms = rooms.filter(Q(name__icontains=q) | Q(description__icontains=q))
    my_handles = request.user.room_handles.select_related("room")
    return render(
        request,
        "rooms/room_list.html",
        {"rooms": rooms, "my_handles": my_handles, "q": q},
    )


@login_required
def room_create_view(request):
    if request.user.role not in {
        User.Role.CLUB_REP,
        User.Role.MODERATOR,
        User.Role.INSTITUTE_ADMIN,
        User.Role.SYSTEM_ADMIN,
    }:
        return HttpResponseForbidden("You do not have permission to create rooms.")
    if request.method == "POST":
        form = DiscussionRoomForm(request.POST, user=request.user)
        if form.is_valid():
            room = form.save(commit=False)
            room.created_by = request.user
            room.save()
            form.save_m2m()
            log_audit(
                action_type=AuditLogEntry.ActionType.ROOM_CREATED,
                acting_user=request.user,
                room=room,
                reason=f"Room {room.name} created.",
            )
            messages.success(request, "Discussion room created successfully.")
            return redirect("rooms:room_detail", pk=room.pk)
    else:
        form = DiscussionRoomForm(user=request.user)
    return render(request, "rooms/room_form.html", {"form": form, "mode": "Create"})


@login_required
def room_edit_view(request, pk):
    room = get_object_or_404(DiscussionRoom, pk=pk)
    _ensure_room_manager(request.user, room)
    if request.method == "POST":
        form = DiscussionRoomForm(request.POST, instance=room, user=request.user)
        if form.is_valid():
            room = form.save()
            messages.success(request, "Discussion room updated.")
            return redirect("rooms:room_detail", pk=room.pk)
    else:
        form = DiscussionRoomForm(instance=room, user=request.user)
    return render(request, "rooms/room_form.html", {"form": form, "mode": "Edit", "room": room})


@login_required
def join_room_view(request, pk):
    room = get_object_or_404(DiscussionRoom, pk=pk, is_archived=False)
    if request.user.is_globally_banned:
        messages.error(request, "You are banned from discussion rooms.")
        return redirect("rooms:room_list")

    existing = RoomHandle.objects.filter(room=room, user=request.user).first()
    if existing:
        if existing.status == RoomHandle.Status.EXPELLED:
            messages.error(request, "You have been expelled from this room.")
            return redirect("rooms:room_list")
        if existing.status == RoomHandle.Status.PENDING:
            messages.info(request, "Your join request is pending approval.")
            return redirect("rooms:room_list")
        return redirect("rooms:room_detail", pk=room.pk)

    if request.method == "POST":
        form = JoinRoomForm(request.POST, room=room)
        if form.is_valid():
            status = (
                RoomHandle.Status.APPROVED
                if room.access_type == DiscussionRoom.AccessType.PUBLIC
                else RoomHandle.Status.PENDING
            )
            approved_at = timezone.now() if status == RoomHandle.Status.APPROVED else None
            RoomHandle.objects.create(
                room=room,
                user=request.user,
                handle_name=form.cleaned_data["handle_name"],
                status=status,
                approved_at=approved_at,
            )
            if status == RoomHandle.Status.APPROVED:
                messages.success(request, "You joined the room successfully.")
                return redirect("rooms:room_detail", pk=room.pk)
            messages.info(request, "Join request submitted for approval.")
            return redirect("rooms:room_list")
    else:
        form = JoinRoomForm(room=room)
    return render(request, "rooms/join_room.html", {"room": room, "form": form})


@login_required
def room_detail_view(request, pk):
    room = get_object_or_404(DiscussionRoom.objects.select_related("club", "event"), pk=pk)
    handle = RoomHandle.objects.filter(room=room, user=request.user).first()
    if not handle:
        messages.info(request, "Choose a handle before entering the room.")
        return redirect("rooms:join_room", pk=room.pk)
    if handle.status == RoomHandle.Status.PENDING:
        return render(request, "rooms/room_pending.html", {"room": room, "handle": handle})
    if handle.status == RoomHandle.Status.EXPELLED:
        messages.error(request, "You have been expelled from this room.")
        return redirect("rooms:room_list")

    if request.method == "POST":
        form = MessageForm(request.POST)
        if form.is_valid():
            if handle.is_muted:
                messages.error(request, "You are muted in this room.")
            else:
                Message.objects.create(
                    room=room,
                    handle=handle,
                    text=form.cleaned_data["text"],
                )
                messages.success(request, "Message posted.")
                return redirect("rooms:room_detail", pk=room.pk)
    else:
        form = MessageForm()

    messages_qs = room.messages.select_related("handle", "handle__user")
    pending_handles = None
    if room.can_be_managed_by(request.user):
        pending_handles = room.room_handles.filter(status=RoomHandle.Status.PENDING)
    return render(
        request,
        "rooms/room_detail.html",
        {
            "room": room,
            "handle": handle,
            "messages_qs": messages_qs,
            "form": form,
            "pending_handles": pending_handles,
            "can_manage_room": room.can_be_managed_by(request.user),
        },
    )


@login_required
def approve_handle_view(request, room_pk, handle_pk):
    room = get_object_or_404(DiscussionRoom, pk=room_pk)
    _ensure_room_manager(request.user, room)
    handle = get_object_or_404(RoomHandle, pk=handle_pk, room=room)
    handle.status = RoomHandle.Status.APPROVED
    handle.approved_at = timezone.now()
    handle.save(update_fields=["status", "approved_at"])
    create_notification(
        user=handle.user,
        text=f"Your join request for room {room.name} has been approved.",
        room=room,
    )
    messages.success(request, "Handle approved.")
    return redirect("rooms:room_detail", pk=room.pk)


@login_required
def reject_handle_view(request, room_pk, handle_pk):
    room = get_object_or_404(DiscussionRoom, pk=room_pk)
    _ensure_room_manager(request.user, room)
    handle = get_object_or_404(RoomHandle, pk=handle_pk, room=room)
    create_notification(
        user=handle.user,
        text=f"Your join request for room {room.name} has been rejected.",
        room=room,
    )
    handle.delete()
    messages.info(request, "Join request rejected.")
    return redirect("rooms:room_detail", pk=room.pk)


@login_required
def message_edit_view(request, room_pk, message_pk):
    room = get_object_or_404(DiscussionRoom, pk=room_pk)
    message_obj = get_object_or_404(Message, pk=message_pk, room=room)
    if not message_obj.can_be_edited_by(request.user):
        messages.error(request, "This message can no longer be edited.")
        return redirect("rooms:room_detail", pk=room.pk)
    if request.method == "POST":
        form = MessageEditForm(request.POST)
        if form.is_valid():
            message_obj.text = form.cleaned_data["text"]
            message_obj.is_edited = True
            message_obj.save(update_fields=["text", "is_edited", "updated_at"])
            messages.success(request, "Message updated.")
            return redirect("rooms:room_detail", pk=room.pk)
    else:
        form = MessageEditForm(initial={"text": message_obj.text})
    return render(
        request,
        "rooms/message_edit.html",
        {"room": room, "message_obj": message_obj, "form": form},
    )


@login_required
def message_delete_view(request, room_pk, message_pk):
    room = get_object_or_404(DiscussionRoom, pk=room_pk)
    message_obj = get_object_or_404(Message, pk=message_pk, room=room)
    if not message_obj.can_be_edited_by(request.user):
        messages.error(request, "This message can no longer be deleted.")
    else:
        message_obj.soft_delete(actor=request.user)
        log_audit(
            action_type=AuditLogEntry.ActionType.MESSAGE_DELETED,
            acting_user=request.user,
            target_user=request.user,
            target_handle_name=message_obj.handle.handle_name,
            room=room,
            message=message_obj,
            reason="User deleted their own message.",
        )
        messages.success(request, "Message deleted.")
    return redirect("rooms:room_detail", pk=room.pk)


@login_required
def report_message_view(request, room_pk, message_pk):
    room = get_object_or_404(DiscussionRoom, pk=room_pk)
    message_obj = get_object_or_404(Message, pk=message_pk, room=room)
    if request.method == "POST":
        form = ReportForm(request.POST)
        if form.is_valid():
            Report.objects.create(
                message=message_obj,
                reporter=request.user,
                reason=form.cleaned_data["reason"],
            )
            messages.success(request, "Message reported successfully.")
            return redirect("rooms:room_detail", pk=room.pk)
    else:
        form = ReportForm()
    return render(
        request,
        "rooms/report_form.html",
        {"room": room, "message_obj": message_obj, "form": form},
    )


@login_required
def moderation_dashboard_view(request):
    forbidden = _ensure_moderator(request.user)
    if forbidden:
        return forbidden
    status = request.GET.get("status", Report.Status.OPEN)
    room_id = request.GET.get("room", "")
    reports = Report.objects.select_related(
        "message", "message__room", "message__handle", "reporter"
    )
    if status:
        reports = reports.filter(status=status)
    if room_id:
        reports = reports.filter(message__room_id=room_id)
    return render(
        request,
        "rooms/moderation_dashboard.html",
        {
            "reports": reports,
            "status": status,
            "rooms": DiscussionRoom.objects.all(),
            "room_id": room_id,
            "status_choices": Report.Status.choices,
        },
    )


@login_required
def moderate_report_view(request, report_pk):
    forbidden = _ensure_moderator(request.user)
    if forbidden:
        return forbidden
    report = get_object_or_404(
        Report.objects.select_related(
            "message", "message__room", "message__handle", "message__handle__user", "reporter"
        ),
        pk=report_pk,
    )
    room = report.message.room
    surrounding_messages = room.messages.filter(
        created_at__gte=report.message.created_at - timedelta(minutes=10),
        created_at__lte=report.message.created_at + timedelta(minutes=10),
    ).select_related("handle")

    if request.method == "POST":
        form = ModerateReportForm(request.POST)
        if form.is_valid():
            action = form.cleaned_data["action"]
            reason = form.cleaned_data["reason"]
            handle = report.message.handle
            target_user = handle.user

            if action == ModerateReportForm.ACTION_DISMISS:
                report.status = Report.Status.DISMISSED
                log_action = AuditLogEntry.ActionType.REPORT_DISMISSED
                notify_text = None
            else:
                report.status = Report.Status.ACTION_TAKEN
                notify_text = None
                if action == ModerateReportForm.ACTION_DELETE:
                    report.message.soft_delete(actor=request.user)
                    log_action = AuditLogEntry.ActionType.MESSAGE_DELETED
                    notify_text = f"A moderator deleted one of your messages in {room.name}."
                elif action == ModerateReportForm.ACTION_MUTE:
                    handle.is_muted = True
                    handle.save(update_fields=["is_muted"])
                    log_action = AuditLogEntry.ActionType.HANDLE_MUTED
                    notify_text = f"You have been muted in {room.name}."
                elif action == ModerateReportForm.ACTION_EXPEL:
                    handle.status = RoomHandle.Status.EXPELLED
                    handle.expelled_at = timezone.now()
                    handle.save(update_fields=["status", "expelled_at"])
                    log_action = AuditLogEntry.ActionType.HANDLE_EXPELLED
                    notify_text = f"You have been expelled from {room.name}."
                elif action == ModerateReportForm.ACTION_REVEAL:
                    handle.status = RoomHandle.Status.EXPELLED
                    handle.revealed_at = timezone.now()
                    handle.expelled_at = timezone.now()
                    handle.save(update_fields=["status", "revealed_at", "expelled_at"])
                    log_action = AuditLogEntry.ActionType.HANDLE_REVEALED
                    notify_text = (
                        f"Your identity was revealed and you were expelled from {room.name}."
                    )
                elif action == ModerateReportForm.ACTION_DELETE_AND_MUTE:
                    report.message.soft_delete(actor=request.user)
                    handle.is_muted = True
                    handle.save(update_fields=["is_muted"])
                    log_action = AuditLogEntry.ActionType.DELETE_AND_MUTE
                    notify_text = (
                        f"A moderator deleted one of your messages and muted you in {room.name}."
                    )
                else:
                    raise Http404

            report.resolved_by = request.user
            report.resolution_reason = reason
            report.resolved_at = timezone.now()
            report.save(update_fields=["status", "resolved_by", "resolution_reason", "resolved_at", "updated_at"])

            log_audit(
                action_type=log_action,
                acting_user=request.user,
                target_user=target_user,
                target_handle_name=handle.handle_name,
                room=room,
                message=report.message,
                reason=reason,
                details={
                    "report_id": str(report.id),
                    "revealed_user": target_user.display_name if action == ModerateReportForm.ACTION_REVEAL else "",
                },
            )
            if notify_text:
                create_notification(
                    user=target_user,
                    text=notify_text,
                    notification_type=Notification.Type.MODERATION_ACTION,
                    room=room,
                    message=report.message,
                )
            messages.success(request, "Moderation action applied.")
            return redirect("rooms:moderation_dashboard")
    else:
        form = ModerateReportForm()
    return render(
        request,
        "rooms/moderate_report.html",
        {
            "report": report,
            "form": form,
            "surrounding_messages": surrounding_messages,
            "revealed_user": report.message.handle.user if report.message.handle.revealed_at else None,
        },
    )
