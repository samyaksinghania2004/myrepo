from django.contrib import admin

from .models import Club, ClubFollow, Event, Registration


@admin.register(Club)
class ClubAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "contact_email", "is_active")
    list_filter = ("category", "is_active")
    search_fields = ("name", "description", "contact_email")
    filter_horizontal = ("representatives",)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "club", "status", "start_time", "capacity")
    list_filter = ("status", "club", "start_time")
    search_fields = ("title", "description", "venue", "tags")


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = ("event", "user", "status", "attendance", "created_at")
    list_filter = ("status", "attendance")
    search_fields = ("event__title", "user__username", "user__email")


@admin.register(ClubFollow)
class ClubFollowAdmin(admin.ModelAdmin):
    list_display = ("club", "user", "created_at")
    search_fields = ("club__name", "user__username", "user__email")
