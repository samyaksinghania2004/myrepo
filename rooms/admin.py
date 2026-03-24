from django.contrib import admin

from .models import DiscussionRoom, Message, Report, RoomHandle


@admin.register(DiscussionRoom)
class DiscussionRoomAdmin(admin.ModelAdmin):
    list_display = ("name", "room_type", "access_type", "is_archived", "created_by")
    list_filter = ("room_type", "access_type", "is_archived")
    search_fields = ("name", "description")
    filter_horizontal = ("moderators",)


@admin.register(RoomHandle)
class RoomHandleAdmin(admin.ModelAdmin):
    list_display = ("handle_name", "room", "user", "status", "is_muted")
    list_filter = ("status", "is_muted", "room")
    search_fields = ("handle_name", "user__username", "room__name")


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("room", "handle", "created_at", "is_edited", "is_deleted")
    list_filter = ("room", "is_edited", "is_deleted")
    search_fields = ("text", "handle__handle_name", "room__name")


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("message", "reporter", "status", "created_at", "resolved_by")
    list_filter = ("status", "created_at")
    search_fields = ("reason", "reporter__username", "message__text")
