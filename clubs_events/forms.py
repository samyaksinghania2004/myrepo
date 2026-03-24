from __future__ import annotations

from django import forms

from accounts.models import User

from .models import Club, Event


class ClubForm(forms.ModelForm):
    class Meta:
        model = Club
        fields = [
            "name",
            "category",
            "description",
            "contact_email",
            "is_active",
            "representatives",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "input"}),
            "category": forms.TextInput(attrs={"class": "input"}),
            "description": forms.Textarea(attrs={"class": "textarea", "rows": 4}),
            "contact_email": forms.EmailInput(attrs={"class": "input"}),
            "representatives": forms.SelectMultiple(attrs={"class": "select is-multiple"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["representatives"].queryset = User.objects.filter(
            role__in=[User.Role.CLUB_REP, User.Role.INSTITUTE_ADMIN, User.Role.SYSTEM_ADMIN]
        ).order_by("username")


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
        ]
        widgets = {
            "club": forms.Select(attrs={"class": "select"}),
            "title": forms.TextInput(attrs={"class": "input"}),
            "description": forms.Textarea(attrs={"class": "textarea", "rows": 4}),
            "venue": forms.TextInput(attrs={"class": "input"}),
            "start_time": forms.DateTimeInput(
                attrs={"class": "input", "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "end_time": forms.DateTimeInput(
                attrs={"class": "input", "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "capacity": forms.NumberInput(attrs={"class": "input", "min": 1}),
            "tags": forms.TextInput(
                attrs={"class": "input", "placeholder": "e.g. technical, workshop"}
            ),
            "status": forms.Select(attrs={"class": "select"}),
        }

    def __init__(self, *args, club_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["start_time"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["end_time"].input_formats = ["%Y-%m-%dT%H:%M"]
        if club_queryset is not None:
            self.fields["club"].queryset = club_queryset


class EventCancellationForm(forms.Form):
    reason = forms.CharField(
        max_length=200,
        widget=forms.Textarea(attrs={"class": "textarea", "rows": 3}),
    )
