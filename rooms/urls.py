from django.urls import path

from . import views

app_name = "rooms"

urlpatterns = [
    path("", views.room_list_view, name="room_list"),
    path("create/", views.room_create_view, name="room_create"),
    path("moderation/", views.moderation_dashboard_view, name="moderation_dashboard"),
    path(
        "moderation/reports/<uuid:report_pk>/",
        views.moderate_report_view,
        name="moderate_report",
    ),
    path("<uuid:pk>/", views.room_detail_view, name="room_detail"),
    path("<uuid:pk>/messages/", views.room_messages_view, name="room_messages"),
    path("<uuid:pk>/send/", views.room_send_view, name="room_send"),
    path("<uuid:pk>/edit/", views.room_edit_view, name="room_edit"),
    path("<uuid:pk>/join/", views.join_room_view, name="join_room"),
    path("<uuid:pk>/leave/", views.leave_room_view, name="leave_room"),
    path("<uuid:pk>/invite/", views.invite_user_view, name="invite_user"),
    path(
        "invites/<uuid:invite_pk>/<str:decision>/",
        views.respond_invite_view,
        name="respond_invite",
    ),
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
