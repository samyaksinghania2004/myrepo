from django.contrib import admin

from .models import Announcement, Club, ClubFollow, ClubMembership, Event, Registration


@admin.register(Club)
class ClubAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "contact_email", "is_active")


@admin.register(ClubMembership)
class ClubMembershipAdmin(admin.ModelAdmin):
    list_display = ("club", "user", "status", "local_role", "joined_at")
    list_filter = ("status", "local_role")


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "club", "status", "start_time", "capacity", "is_archived")


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = ("event", "user", "status", "attendance", "created_at")


@admin.register(ClubFollow)
class ClubFollowAdmin(admin.ModelAdmin):
    list_display = ("club", "user", "created_at")


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "target_type", "created_at", "is_active")
