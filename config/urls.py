from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from core import views as core_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("manifest.webmanifest", core_views.web_manifest_view, name="web_manifest"),
    path("service-worker.js", core_views.service_worker_view, name="service_worker"),
    path("accounts/", include("accounts.urls")),
    path("", include("core.urls")),
    path("clubs/", include("clubs_events.urls")),
    path("rooms/", include("rooms.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
