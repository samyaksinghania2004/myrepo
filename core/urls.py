from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.root_redirect, name="root"),
    path("offline/", views.offline_view, name="offline"),
    path("notifications/", views.notifications_list_view, name="notifications"),
    path("notifications/feed/", views.notifications_feed_view, name="notifications_feed"),
    path(
        "notifications/<uuid:pk>/open/",
        views.open_notification_view,
        name="open_notification",
    ),
    path(
        "notifications/<uuid:pk>/read/",
        views.mark_notification_read_view,
        name="mark_notification_read",
    ),
    path("search/", views.search_view, name="search"),
    path("inbox/", views.inbox_view, name="inbox"),
    path("inbox/<uuid:thread_pk>/", views.inbox_thread_view, name="inbox_thread"),
    path(
        "inbox/<uuid:thread_pk>/block/<str:action>/",
        views.inbox_block_view,
        name="inbox_block",
    ),
    path(
        "inbox/<uuid:thread_pk>/messages/",
        views.inbox_messages_view,
        name="inbox_messages",
    ),
    path(
        "inbox/<uuid:thread_pk>/send/",
        views.inbox_send_view,
        name="inbox_send",
    ),
    path("users/search/", views.user_search_view, name="user_search"),
    path("help/", views.help_view, name="help"),
]
