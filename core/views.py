from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.db import models
from django.shortcuts import get_object_or_404, redirect, render

from clubs_events.models import Club, Event
from rooms.models import DiscussionRoom

from .forms import SearchForm
from .models import Notification


def root_redirect(request):
    if request.user.is_authenticated:
        return redirect("clubs_events:event_feed")
    return redirect("accounts:login")


@login_required
def notifications_list_view(request):
    notifications = request.user.notifications.select_related("event", "room").all()
    if request.method == "POST":
        notifications.filter(is_read=False).update(is_read=True)
        return redirect("core:notifications")
    return render(
        request,
        "core/notifications_list.html",
        {"notifications": notifications},
    )


@login_required
def mark_notification_read_view(request, pk):
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    notification.is_read = True
    notification.save(update_fields=["is_read"])
    return redirect("core:notifications")


@login_required
def search_view(request):
    form = SearchForm(request.GET or None)
    query = ""
    clubs = Club.objects.none()
    events = Event.objects.none()
    rooms = DiscussionRoom.objects.none()
    if form.is_valid():
        query = form.cleaned_data["q"].strip()
        if query:
            clubs = Club.objects.filter(is_active=True).filter(
                models.Q(name__icontains=query)
                | models.Q(description__icontains=query)
                | models.Q(category__icontains=query)
            )
            events = Event.objects.filter(status=Event.Status.PUBLISHED).filter(
                models.Q(title__icontains=query)
                | models.Q(description__icontains=query)
                | models.Q(tags__icontains=query)
                | models.Q(club__name__icontains=query)
            )
            rooms = DiscussionRoom.objects.filter(is_archived=False).filter(
                models.Q(name__icontains=query)
                | models.Q(description__icontains=query)
            )

    return render(
        request,
        "core/search_results.html",
        {
            "form": form,
            "query": query,
            "clubs": clubs,
            "events": events,
            "rooms": rooms,
        },
    )


def help_view(request):
    return render(request, "core/help.html")
