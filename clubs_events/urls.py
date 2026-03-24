from django.urls import path

from . import views

app_name = "clubs_events"

urlpatterns = [
    path("", views.event_feed_view, name="event_feed"),
    path("my-events/", views.my_events_view, name="my_events"),
    path("analytics/", views.analytics_dashboard_view, name="analytics_dashboard"),
    path("manage/clubs/create/", views.club_create_view, name="club_create"),
    path("manage/clubs/<uuid:pk>/edit/", views.club_edit_view, name="club_edit"),
    path("all/", views.club_list_view, name="club_list"),
    path("<uuid:pk>/", views.club_detail_view, name="club_detail"),
    path("<uuid:pk>/follow-toggle/", views.club_follow_toggle_view, name="club_follow_toggle"),
    path("events/create/", views.event_create_view, name="event_create"),
    path("events/<uuid:pk>/", views.event_detail_view, name="event_detail"),
    path("events/<uuid:pk>/edit/", views.event_edit_view, name="event_edit"),
    path("events/<uuid:pk>/cancel/", views.event_cancel_view, name="event_cancel"),
    path("events/<uuid:pk>/register/", views.event_register_view, name="event_register"),
    path(
        "events/<uuid:pk>/cancel-registration/",
        views.event_cancel_registration_view,
        name="event_cancel_registration",
    ),
    path(
        "events/<uuid:pk>/attendance/",
        views.attendance_manage_view,
        name="attendance_manage",
    ),
]
