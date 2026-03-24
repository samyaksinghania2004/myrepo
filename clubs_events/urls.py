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
    path("<uuid:pk>/join/", views.club_join_view, name="club_join"),
    path("<uuid:pk>/leave/", views.club_leave_view, name="club_leave"),
    path("<uuid:pk>/members/<int:user_id>/assign-secretary/", views.assign_secretary_view, name="assign_secretary"),
    path("<uuid:pk>/members/<int:user_id>/revoke-secretary/", views.revoke_secretary_view, name="revoke_secretary"),
    path("events/create/", views.event_create_view, name="event_create"),
    path("events/<uuid:pk>/", views.event_detail_view, name="event_detail"),
    path("events/<uuid:pk>/edit/", views.event_edit_view, name="event_edit"),
    path("events/<uuid:pk>/cancel/", views.event_cancel_view, name="event_cancel"),
    path("events/<uuid:pk>/register/", views.event_register_view, name="event_register"),
    path("events/<uuid:pk>/cancel-registration/", views.event_cancel_registration_view, name="event_cancel_registration"),
    path("events/<uuid:pk>/attendance/", views.attendance_manage_view, name="attendance_manage"),
    path("announcements/<str:target_type>/<uuid:pk>/create/", views.announcement_create_view, name="announcement_create"),
]
