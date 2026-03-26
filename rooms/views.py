from __future__ import annotations

from datetime import timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.db import IntegrityError
from django.db.models import Count, Q
from django.contrib.auth.decorators import login_required
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
    can_create_room,
    can_manage_room,
    can_view_reports,
)
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
    q = request.GET.get("q", "").strip()[:50]
    rooms = DiscussionRoom.objects.filter(
        is_archived=False, room_type=DiscussionRoom.RoomType.TOPIC
    )
    if q:
        rooms = rooms.filter(name__icontains=q) | rooms.filter(description__icontains=q)
    rooms = rooms.annotate(
        active_handles_count=Count(
            "room_handles",
            filter=Q(room_handles__status=RoomHandle.Status.APPROVED),
            distinct=True,
        )
    )
    return render(
        request,
        "rooms/room_list.html",
        {
            "rooms": rooms.distinct(),
            "q": q,
            "my_handles": request.user.room_handles.filter(
                status=RoomHandle.Status.APPROVED,
                room__is_archived=False,
            )
            .select_related("room")
            .order_by("room__name"),
            "can_create_room_any": True,
        },
    )


@login_required
def room_create_view(request):
    if not can_create_room(request.user):
        return HttpResponseForbidden("You do not have permission to create rooms.")

    active_count = DiscussionRoom.objects.filter(
        created_by=request.user,
        room_type=DiscussionRoom.RoomType.TOPIC,
        is_archived=False,
    ).count()
    if active_count >= 5:
        messages.error(
            request,
            "You have reached the limit of 5 active open rooms. Archive an old room to create a new one.",
        )
        return redirect("rooms:room_list")

    form = DiscussionRoomForm(request.POST or None, show_archive=False)
    if request.method == "POST" and form.is_valid():
        room = form.save(commit=False)
        room.room_type = DiscussionRoom.RoomType.TOPIC
        room.club = None
        room.event = None
        room.created_by = request.user
        room.save()
        messages.success(request, "Open room created. Set your handle to join.")
        log_audit(
            action_type=AuditLogEntry.ActionType.ROOM_CREATED,
            acting_user=request.user,
            room=room,
        )
        return redirect("rooms:join_room", pk=room.pk)
    return render(request, "rooms/room_form.html", {"form": form, "mode": "Create"})


@login_required
def room_edit_view(request, pk):
    room = get_object_or_404(DiscussionRoom.objects.select_related("club", "event"), pk=pk)
    if not can_manage_room(request.user, room):
        raise Http404
    form = DiscussionRoomForm(request.POST or None, instance=room, show_archive=True)
    if request.method == "POST" and form.is_valid():
        room = form.save()
        messages.success(request, "Room updated.")
        log_audit(
            action_type=AuditLogEntry.ActionType.ROOM_UPDATED,
            acting_user=request.user,
            room=room,
        )
        return redirect("rooms:room_detail", pk=room.pk)
    return render(request, "rooms/room_form.html", {"form": form, "mode": "Edit", "room": room})


def _invite_allows_join(room, user):
    if room.created_by_id == user.id:
        return True
    if room.access_type != DiscussionRoom.AccessType.PRIVATE_INVITE_ONLY:
        return True
    invite = RoomInvite.objects.filter(
        room=room,
        recipient=user,
        status__in=[RoomInvite.Status.PENDING, RoomInvite.Status.ACCEPTED],
    ).first()
    if invite is None:
        return False
    if invite.expires_at and invite.expires_at < timezone.now():
        return False
    return True


def _room_access_state(room, user):
    manager_access = can_manage_room(user, room)
    can_review_reports = can_view_reports(user)
    handle = RoomHandle.objects.filter(room=room, user=user).first()
    read_only_mode = False
    if not handle:
        if manager_access or can_review_reports:
            read_only_mode = True
        else:
            return handle, False, manager_access, can_review_reports, False
    elif handle.status == RoomHandle.Status.PENDING:
        if manager_access or can_review_reports:
            read_only_mode = True
        else:
            return handle, False, manager_access, can_review_reports, False
    elif handle.status == RoomHandle.Status.EXPELLED:
        return handle, False, manager_access, can_review_reports, False
    elif handle.status == RoomHandle.Status.LEFT:
        return handle, False, manager_access, can_review_reports, False
    return handle, True, manager_access, can_review_reports, read_only_mode


def _serialize_room_message(message, viewer, show_real_identities, manager_access):
    created_at = timezone.localtime(message.created_at)
    identity = ""
    if show_real_identities and message.handle and message.handle.user:
        identity = f"{message.handle.user.display_name} ({message.handle.user.email})"
    body_html = (
        "This message was deleted by the author or a moderator."
        if message.is_deleted
        else str(linebreaksbr(escape(message.text)))
    )
    return {
        "id": str(message.id),
        "handle_name": message.handle.handle_name if message.handle else "Unknown",
        "identity": identity,
        "created_at": message.created_at.isoformat(),
        "created_at_display": date_format(created_at, "DATETIME_FORMAT"),
        "is_edited": message.is_edited,
        "is_deleted": message.is_deleted,
        "body_html": body_html,
        "can_edit": message.can_be_edited_by(viewer),
        "can_delete": message.can_be_deleted_by(viewer) or manager_access,
        "can_report": not message.is_deleted and message.handle.user_id != viewer.id,
        "edit_url": reverse("rooms:message_edit", args=[message.room_id, message.id]),
        "delete_url": reverse("rooms:message_delete", args=[message.room_id, message.id]),
        "report_url": reverse("rooms:report_message", args=[message.room_id, message.id]),
    }


@login_required
def join_room_view(request, pk):
    room = get_object_or_404(DiscussionRoom, pk=pk, is_archived=False)
    if request.user.is_globally_banned:
        messages.error(request, "Your account is blocked from room participation.")
        return redirect("rooms:room_list")
    existing = RoomHandle.objects.filter(room=room, user=request.user).first()
    if existing and existing.status == RoomHandle.Status.EXPELLED:
        messages.error(request, "You cannot rejoin this room.")
        return redirect("rooms:room_list")
    if existing and existing.status == RoomHandle.Status.APPROVED:
        return redirect("rooms:room_detail", pk=room.pk)
    if existing and existing.status == RoomHandle.Status.PENDING:
        messages.info(request, "Your join request is still pending approval.")
        return redirect("rooms:room_list")
    if not _invite_allows_join(room, request.user):
        return HttpResponseForbidden("Invite required for this room.")

    form = JoinRoomForm(
        request.POST or None,
        room=room,
        existing_handle=existing if existing and existing.status == RoomHandle.Status.LEFT else None,
    )
    if request.method == "POST" and form.is_valid():
        status = RoomHandle.Status.APPROVED
        if room.room_type in {
            DiscussionRoom.RoomType.CLUB,
            DiscussionRoom.RoomType.EVENT,
        } and room.access_type in {
            DiscussionRoom.AccessType.CLUB_ONLY,
            DiscussionRoom.AccessType.EVENT_ONLY,
        }:
            status = RoomHandle.Status.PENDING
        try:
            if existing and existing.status == RoomHandle.Status.LEFT:
                existing.handle_name = form.cleaned_data["handle_name"]
                existing.status = status
                existing.is_muted = False
                existing.expelled_at = None
                existing.approved_at = timezone.now() if status == RoomHandle.Status.APPROVED else None
                existing.save(
                    update_fields=[
                        "handle_name",
                        "status",
                        "is_muted",
                        "expelled_at",
                        "approved_at",
                    ]
                )
            else:
                RoomHandle.objects.create(
                    room=room,
                    user=request.user,
                    handle_name=form.cleaned_data["handle_name"],
                    status=status,
                    approved_at=timezone.now() if status == RoomHandle.Status.APPROVED else None,
                )
        except IntegrityError:
            form.add_error("handle_name", "This handle is already taken in the room.")
            return render(request, "rooms/join_room.html", {"room": room, "form": form})
        pending_invite = RoomInvite.objects.filter(
            room=room,
            recipient=request.user,
            status=RoomInvite.Status.PENDING,
        ).first()
        if pending_invite:
            pending_invite.status = RoomInvite.Status.ACCEPTED
            pending_invite.save(update_fields=["status", "updated_at"])
        if status == RoomHandle.Status.APPROVED:
            messages.success(request, f"You joined {room.name}.")
            return redirect("rooms:room_detail", pk=room.pk)
    return render(request, "rooms/join_room.html", {"room": room, "form": form})


@login_required
def leave_room_view(request, pk):
    room = get_object_or_404(DiscussionRoom, pk=pk)
    handle = get_object_or_404(RoomHandle, room=room, user=request.user)
    if request.method == "POST":
        handle.status = RoomHandle.Status.LEFT
        handle.is_muted = False
        handle.save(update_fields=["status", "is_muted"])
        if room.access_type == DiscussionRoom.AccessType.PRIVATE_INVITE_ONLY:
            RoomInvite.objects.filter(
                room=room,
                recipient=request.user,
            ).exclude(status=RoomInvite.Status.REVOKED).update(
                status=RoomInvite.Status.REVOKED,
                updated_at=timezone.now(),
            )
        messages.info(request, f"You left {room.name}. You can rejoin later with a fresh request.")
    return redirect("rooms:room_list")


@login_required
def room_detail_view(request, pk):
    room = get_object_or_404(DiscussionRoom.objects.select_related("club", "event", "event__club"), pk=pk)
    can_review_reports = can_view_reports(request.user)
    manager_access = can_manage_room(request.user, room)
    handle = RoomHandle.objects.filter(room=room, user=request.user).first()
    read_only_mode = False

    if not handle:
        if manager_access or can_review_reports:
            read_only_mode = True
        else:
            return redirect("rooms:join_room", pk=room.pk)
    elif handle.status == RoomHandle.Status.PENDING:
        if manager_access or can_review_reports:
            read_only_mode = True
        else:
            return render(request, "rooms/room_pending.html", {"room": room, "handle": handle})
    elif handle.status == RoomHandle.Status.EXPELLED:
        return redirect("rooms:room_list")
    elif handle.status == RoomHandle.Status.LEFT:
        return redirect("rooms:join_room", pk=room.pk)

    form = MessageForm(request.POST or None)
    if request.method == "POST":
        if read_only_mode or not handle or not handle.can_post:
            messages.error(request, "You cannot post in this room right now.")
            return redirect("rooms:room_detail", pk=room.pk)
        if form.is_valid():
            Message.objects.create(room=room, handle=handle, text=form.cleaned_data["text"])
            return redirect("rooms:room_detail", pk=room.pk)

    messages_qs = room.messages.select_related("handle", "handle__user")
    focus_message_id = request.GET.get("focus", "")
    participants = room.room_handles.filter(
        status=RoomHandle.Status.APPROVED
    ).select_related("user").order_by("handle_name")
    editable_message_ids = []
    deletable_message_ids = []
    for message_obj in messages_qs:
        if message_obj.can_be_edited_by(request.user):
            editable_message_ids.append(message_obj.pk)
        if message_obj.can_be_deleted_by(request.user) or manager_access:
            deletable_message_ids.append(message_obj.pk)
    last_message_at = messages_qs.last().created_at if messages_qs else None

    return render(
        request,
        "rooms/room_detail.html",
        {
            "room": room,
            "handle": handle,
            "messages_qs": messages_qs,
            "form": form,
            "pending_handles": room.room_handles.filter(status=RoomHandle.Status.PENDING).select_related("user") if manager_access else None,
            "can_manage_room": manager_access,
            "invites": room.invites.select_related("recipient") if manager_access else None,
            "invite_form": RoomInviteForm(room=room, inviter=request.user),
            "read_only_mode": read_only_mode,
            "focus_message_id": focus_message_id,
            "review_mode": request.GET.get("review") == "1",
            "show_real_identities": can_review_reports,
            "participants": participants,
            "editable_message_ids": editable_message_ids,
            "deletable_message_ids": deletable_message_ids,
            "last_message_at": last_message_at,
        },
    )


@login_required
def room_messages_view(request, pk):
    room = get_object_or_404(
        DiscussionRoom.objects.select_related("club", "event", "event__club"),
        pk=pk,
        is_archived=False,
    )
    handle, can_view, manager_access, can_review_reports, _ = _room_access_state(
        room, request.user
    )
    if not can_view:
        return JsonResponse({"error": "not_allowed"}, status=403)
    messages_qs = room.messages.select_related("handle", "handle__user")
    since = request.GET.get("since", "").strip()
    if since:
        parsed = parse_datetime(since)
        if parsed:
            if timezone.is_naive(parsed):
                parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
            messages_qs = messages_qs.filter(created_at__gt=parsed)
    items = [
        _serialize_room_message(message, request.user, can_review_reports, manager_access)
        for message in messages_qs
    ]
    return JsonResponse({"items": items})


@login_required
def room_send_view(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    room = get_object_or_404(
        DiscussionRoom.objects.select_related("club", "event", "event__club"),
        pk=pk,
        is_archived=False,
    )
    handle, can_view, manager_access, can_review_reports, read_only_mode = _room_access_state(
        room, request.user
    )
    if not can_view or read_only_mode or not handle or not handle.can_post:
        return JsonResponse({"error": "not_allowed"}, status=403)
    form = MessageForm(request.POST)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors}, status=400)
    message = Message.objects.create(room=room, handle=handle, text=form.cleaned_data["text"])
    return JsonResponse(
        {
            "item": _serialize_room_message(
                message, request.user, can_review_reports, manager_access
            )
        }
    )


@login_required
def invite_user_view(request, pk):
    room = get_object_or_404(DiscussionRoom, pk=pk)
    if not can_manage_room(request.user, room):
        return HttpResponseForbidden("Not allowed")
    if room.access_type != DiscussionRoom.AccessType.PRIVATE_INVITE_ONLY:
        return HttpResponseForbidden("Invites are only available for private rooms.")
    form = RoomInviteForm(request.POST or None, room=room, inviter=request.user)
    if request.method == "POST":
        if form.is_valid():
            invite, _ = RoomInvite.objects.update_or_create(
                room=room,
                recipient=form.cleaned_data["recipient"],
                defaults={"status": RoomInvite.Status.PENDING, "invited_by": request.user},
            )
            create_notification(
                user=invite.recipient,
                text=f"Invite to {room.name}",
                body=f"{request.user.display_name} invited you to join {room.name}. Open this notification to review the room.",
                notification_type=Notification.Type.INVITE,
                room=room,
                action_url=reverse("rooms:join_room", args=[room.pk]),
            )
            log_audit(
                action_type=AuditLogEntry.ActionType.ROOM_INVITE_CREATED,
                acting_user=request.user,
                room=room,
                target_user=invite.recipient,
            )
            messages.success(request, f"Invite sent to {invite.recipient.display_name}.")
        else:
            for error_list in form.errors.values():
                for error in error_list:
                    messages.error(request, error)
    return redirect("rooms:room_detail", pk=room.pk)


@login_required
def respond_invite_view(request, invite_pk, decision):
    invite = get_object_or_404(RoomInvite, pk=invite_pk, recipient=request.user)
    if invite.status != RoomInvite.Status.PENDING:
        return redirect("core:notifications")
    invite.status = (
        RoomInvite.Status.ACCEPTED if decision == "accept" else RoomInvite.Status.REJECTED
    )
    invite.save(update_fields=["status", "updated_at"])
    log_audit(
        action_type=AuditLogEntry.ActionType.ROOM_INVITE_UPDATED,
        acting_user=request.user,
        room=invite.room,
        details={"status": invite.status},
    )
    return (
        redirect("rooms:join_room", pk=invite.room_id)
        if decision == "accept"
        else redirect("core:notifications")
    )


@login_required
def approve_handle_view(request, room_pk, handle_pk):
    room = get_object_or_404(DiscussionRoom, pk=room_pk)
    if not can_manage_room(request.user, room):
        raise Http404
    handle = get_object_or_404(RoomHandle, pk=handle_pk, room=room)
    handle.status = RoomHandle.Status.APPROVED
    handle.approved_at = timezone.now()
    handle.save(update_fields=["status", "approved_at"])
    messages.success(request, f"{handle.handle_name} can now enter the room.")
    return redirect("rooms:room_detail", pk=room.pk)


@login_required
def reject_handle_view(request, room_pk, handle_pk):
    room = get_object_or_404(DiscussionRoom, pk=room_pk)
    if not can_manage_room(request.user, room):
        raise Http404
    handle = get_object_or_404(RoomHandle, pk=handle_pk, room=room)
    handle.delete()
    messages.info(request, "Join request rejected.")
    return redirect("rooms:room_detail", pk=room.pk)


@login_required
def message_edit_view(request, room_pk, message_pk):
    room = get_object_or_404(DiscussionRoom, pk=room_pk)
    message_obj = get_object_or_404(Message, pk=message_pk, room=room)
    if not message_obj.can_be_edited_by(request.user):
        messages.error(request, "That message can no longer be edited.")
        return redirect("rooms:room_detail", pk=room.pk)
    form = MessageEditForm(request.POST or None, initial={"text": message_obj.text})
    if request.method == "POST" and form.is_valid():
        message_obj.text = form.cleaned_data["text"]
        message_obj.is_edited = True
        message_obj.save(update_fields=["text", "is_edited", "updated_at"])
        messages.success(request, "Message updated.")
        return redirect("rooms:room_detail", pk=room.pk)
    return render(
        request,
        "rooms/message_edit.html",
        {"room": room, "message_obj": message_obj, "form": form},
    )


@login_required
def message_delete_view(request, room_pk, message_pk):
    room = get_object_or_404(DiscussionRoom, pk=room_pk)
    message_obj = get_object_or_404(Message, pk=message_pk, room=room)
    if message_obj.can_be_deleted_by(request.user) or can_manage_room(request.user, room):
        message_obj.soft_delete(actor=request.user)
        messages.info(request, "Message deleted.")
    else:
        messages.error(request, "You are not allowed to delete that message.")
    return redirect("rooms:room_detail", pk=room.pk)


@login_required
def report_message_view(request, room_pk, message_pk):
    room = get_object_or_404(DiscussionRoom, pk=room_pk)
    message_obj = get_object_or_404(Message, pk=message_pk, room=room)
    if message_obj.handle.user_id == request.user.id:
        messages.error(request, "You cannot report your own message.")
        return redirect("rooms:room_detail", pk=room.pk)
    if message_obj.is_deleted:
        messages.error(request, "Deleted messages cannot be reported.")
        return redirect("rooms:room_detail", pk=room.pk)

    form = ReportForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        Report.objects.create(
            message=message_obj,
            reporter=request.user,
            reason=form.cleaned_data["reason"],
        )
        messages.success(request, "The report has been submitted for admin review.")
        return redirect("rooms:room_detail", pk=room.pk)
    return render(
        request,
        "rooms/report_form.html",
        {"room": room, "message_obj": message_obj, "form": form},
    )


@login_required
def moderation_dashboard_view(request):
    if not can_view_reports(request.user):
        return HttpResponseForbidden("Only institute and system admins can access this page.")
    reports = Report.objects.select_related(
        "message",
        "message__room",
        "message__handle",
        "message__handle__user",
        "reporter",
    )
    status = request.GET.get("status", "")
    room_id = request.GET.get("room", "")
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
            "room_id": room_id,
            "rooms": DiscussionRoom.objects.all(),
            "status_choices": Report.Status.choices,
        },
    )


@login_required
def moderate_report_view(request, report_pk):
    if not can_view_reports(request.user):
        return HttpResponseForbidden("Only institute and system admins can access this page.")
    report = get_object_or_404(
        Report.objects.select_related(
            "message",
            "message__room",
            "message__handle",
            "message__handle__user",
            "reporter",
        ),
        pk=report_pk,
    )
    room = report.message.room
    surrounding_messages = (
        room.messages.filter(
            created_at__gte=report.message.created_at - timedelta(minutes=10),
            created_at__lte=report.message.created_at + timedelta(minutes=10),
        )
        .select_related("handle", "handle__user")
        .order_by("created_at")
    )
    participants = []
    participant_ids = set()
    for item in surrounding_messages:
        if item.handle.user_id in participant_ids:
            continue
        participant_ids.add(item.handle.user_id)
        participants.append(item.handle)

    focus_query = urlencode({"focus": str(report.message.pk), "review": 1, "report": str(report.pk)})
    jump_url = f"{reverse('rooms:room_detail', args=[room.pk])}?{focus_query}"

    form = ModerateReportForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        action = form.cleaned_data["action"]
        reason = form.cleaned_data["reason"]
        handle = report.message.handle
        acted = False

        if action == ModerateReportForm.ACTION_DISMISS:
            report.status = Report.Status.DISMISSED
            log_audit(
                action_type=AuditLogEntry.ActionType.REPORT_DISMISSED,
                acting_user=request.user,
                room=room,
                message=report.message,
                reason=reason,
            )
        else:
            report.status = Report.Status.ACTION_TAKEN
            if action in {
                ModerateReportForm.ACTION_DELETE,
                ModerateReportForm.ACTION_DELETE_AND_MUTE,
            } and not report.message.is_deleted:
                report.message.soft_delete(actor=request.user)
                acted = True
                log_audit(
                    action_type=AuditLogEntry.ActionType.MESSAGE_DELETED,
                    acting_user=request.user,
                    room=room,
                    message=report.message,
                    reason=reason,
                )
            if action in {
                ModerateReportForm.ACTION_MUTE,
                ModerateReportForm.ACTION_DELETE_AND_MUTE,
            }:
                handle.is_muted = True
                handle.save(update_fields=["is_muted"])
                acted = True
                log_audit(
                    action_type=AuditLogEntry.ActionType.HANDLE_MUTED,
                    acting_user=request.user,
                    target_user=handle.user,
                    target_handle_name=handle.handle_name,
                    room=room,
                    reason=reason,
                )
            if action in {
                ModerateReportForm.ACTION_EXPEL,
                ModerateReportForm.ACTION_REVEAL,
            }:
                handle.status = RoomHandle.Status.EXPELLED
                handle.expelled_at = timezone.now()
                handle.save(update_fields=["status", "expelled_at"])
                acted = True
                log_audit(
                    action_type=AuditLogEntry.ActionType.HANDLE_EXPELLED,
                    acting_user=request.user,
                    target_user=handle.user,
                    target_handle_name=handle.handle_name,
                    room=room,
                    reason=reason,
                )
            if action == ModerateReportForm.ACTION_REVEAL:
                handle.revealed_at = timezone.now()
                handle.save(update_fields=["revealed_at"])
                acted = True
                log_audit(
                    action_type=AuditLogEntry.ActionType.HANDLE_REVEALED,
                    acting_user=request.user,
                    target_user=handle.user,
                    target_handle_name=handle.handle_name,
                    room=room,
                    reason=reason,
                )
            if not acted:
                report.status = Report.Status.IN_REVIEW

        report.resolved_by = request.user
        report.resolution_reason = reason
        report.resolved_at = timezone.now()
        report.save(
            update_fields=[
                "status",
                "resolved_by",
                "resolution_reason",
                "resolved_at",
                "updated_at",
            ]
        )
        create_notification(
            user=report.reporter,
            text=f"Your report in {room.name} was reviewed",
            body=reason,
            notification_type=Notification.Type.MODERATION_ACTION,
            room=room,
            message=report.message,
            action_url=jump_url,
        )
        messages.success(request, "Report resolution saved.")
        return redirect("rooms:moderate_report", report_pk=report.pk)

    return render(
        request,
        "rooms/moderate_report.html",
        {
            "report": report,
            "room": room,
            "form": form,
            "surrounding_messages": surrounding_messages,
            "participants": participants,
            "jump_url": jump_url,
        },
    )
