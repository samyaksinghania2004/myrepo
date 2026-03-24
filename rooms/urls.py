from django.urls import path

from . import views

app_name = "rooms"

urlpatterns = [
    path("", views.room_list_view, name="room_list"),
    path("create/", views.room_create_view, name="room_create"),
    path("moderation/", views.moderation_dashboard_view, name="moderation_dashboard"),
    path("moderation/reports/<uuid:report_pk>/", views.moderate_report_view, name="moderate_report"),
    path("<uuid:pk>/", views.room_detail_view, name="room_detail"),
    path("<uuid:pk>/edit/", views.room_edit_view, name="room_edit"),
    path("<uuid:pk>/join/", views.join_room_view, name="join_room"),
    path(
        "<uuid:room_pk>/handles/<uuid:handle_pk>/approve/",
        views.approve_handle_view,
        name="approve_handle",
    ),
    path(
        "<uuid:room_pk>/handles/<uuid:handle_pk>/reject/",
        views.reject_handle_view,
        name="reject_handle",
    ),
    path(
        "<uuid:room_pk>/messages/<uuid:message_pk>/edit/",
        views.message_edit_view,
        name="message_edit",
    ),
    path(
        "<uuid:room_pk>/messages/<uuid:message_pk>/delete/",
        views.message_delete_view,
        name="message_delete",
    ),
    path(
        "<uuid:room_pk>/messages/<uuid:message_pk>/report/",
        views.report_message_view,
        name="report_message",
    ),
]
