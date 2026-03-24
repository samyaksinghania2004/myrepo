from __future__ import annotations

from django import forms

from accounts.models import User

from .models import Announcement, Club, ClubMembership, Event


class ClubForm(forms.ModelForm):
    class Meta:
        model = Club
        fields = ["name", "category", "description", "contact_email", "is_active"]


class ClubSecretaryForm(forms.Form):
    user = forms.ModelChoiceField(queryset=None)

    def __init__(self, *args, club=None, **kwargs):
        super().__init__(*args, **kwargs)
        active_ids = club.memberships.filter(
            status=ClubMembership.Status.ACTIVE,
        ).values_list("user_id", flat=True)
        self.fields["user"].queryset = User.objects.filter(id__in=active_ids)


class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = [
            "club",
            "title",
            "description",
            "venue",
            "start_time",
            "end_time",
            "capacity",
            "tags",
            "status",
            "waitlist_enabled",
            "is_archived",
        ]
        widgets = {
            "start_time": forms.DateTimeInput(
                attrs={"class": "input", "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "end_time": forms.DateTimeInput(
                attrs={"class": "input", "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
        }

    def __init__(self, *args, club_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["start_time"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["end_time"].input_formats = ["%Y-%m-%dT%H:%M"]
        if club_queryset is not None:
            self.fields["club"].queryset = club_queryset


class EventCancellationForm(forms.Form):
    reason = forms.CharField(max_length=200, widget=forms.Textarea(attrs={"rows": 3}))


class AnnouncementForm(forms.ModelForm):
    class Meta:
        model = Announcement
        fields = ["title", "body"]
