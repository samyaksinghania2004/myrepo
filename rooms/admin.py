from django.contrib import admin

from .models import DiscussionRoom, Message, Report, RoomHandle, RoomInvite


@admin.register(DiscussionRoom)
class DiscussionRoomAdmin(admin.ModelAdmin):
    list_display = ("name", "room_type", "access_type", "is_archived", "created_by")


@admin.register(RoomHandle)
class RoomHandleAdmin(admin.ModelAdmin):
    list_display = ("handle_name", "room", "user", "status", "is_muted")


@admin.register(RoomInvite)
class RoomInviteAdmin(admin.ModelAdmin):
    list_display = ("room", "recipient", "status", "invited_by", "created_at")


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("room", "handle", "created_at", "is_deleted")


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("message", "reporter", "status", "created_at", "resolved_by")
