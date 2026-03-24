from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.root_redirect, name="root"),
    path("notifications/", views.notifications_list_view, name="notifications"),
    path(
        "notifications/<uuid:pk>/read/",
        views.mark_notification_read_view,
        name="mark_notification_read",
    ),
    path("search/", views.search_view, name="search"),
    path("help/", views.help_view, name="help"),
]
