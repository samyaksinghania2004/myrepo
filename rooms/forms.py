from __future__ import annotations

from django import forms

from accounts.models import User
from clubs_events.models import Club, Event

from .models import DiscussionRoom, Report


class DiscussionRoomForm(forms.ModelForm):
    class Meta:
        model = DiscussionRoom
        fields = [
            "name",
            "description",
            "room_type",
            "access_type",
            "club",
            "event",
            "moderators",
            "is_archived",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "input"}),
            "description": forms.Textarea(attrs={"class": "textarea", "rows": 4}),
            "room_type": forms.Select(attrs={"class": "select"}),
            "access_type": forms.Select(attrs={"class": "select"}),
            "club": forms.Select(attrs={"class": "select"}),
            "event": forms.Select(attrs={"class": "select"}),
            "moderators": forms.SelectMultiple(attrs={"class": "select is-multiple"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["moderators"].queryset = User.objects.filter(
            role__in=[User.Role.MODERATOR, User.Role.INSTITUTE_ADMIN, User.Role.SYSTEM_ADMIN]
        ).order_by("username")
        if user and user.role == User.Role.CLUB_REP:
            clubs = user.represented_clubs.all()
            self.fields["club"].queryset = clubs
            self.fields["event"].queryset = Event.objects.filter(club__in=clubs)
        else:
            self.fields["club"].queryset = Club.objects.filter(is_active=True)
            self.fields["event"].queryset = Event.objects.all()


class JoinRoomForm(forms.Form):
    handle_name = forms.CharField(
        max_length=24,
        widget=forms.TextInput(attrs={"class": "input", "placeholder": "Choose a handle"}),
    )

    def __init__(self, *args, room=None, **kwargs):
        self.room = room
        super().__init__(*args, **kwargs)

    def clean_handle_name(self):
        handle_name = self.cleaned_data["handle_name"].strip()
        if self.room and self.room.room_handles.filter(handle_name__iexact=handle_name).exists():
            raise forms.ValidationError("This handle is already taken in the room.")
        return handle_name


class MessageForm(forms.Form):
    text = forms.CharField(
        max_length=1000,
        widget=forms.Textarea(
            attrs={"class": "textarea", "rows": 3, "placeholder": "Type your message here..."}
        ),
    )


class MessageEditForm(forms.Form):
    text = forms.CharField(
        max_length=1000,
        widget=forms.Textarea(attrs={"class": "textarea", "rows": 3}),
    )


class ReportForm(forms.ModelForm):
    class Meta:
        model = Report
        fields = ["reason"]
        widgets = {
            "reason": forms.Textarea(
                attrs={
                    "class": "textarea",
                    "rows": 3,
                    "placeholder": "Optional reason for the report",
                }
            )
        }


class ModerateReportForm(forms.Form):
    ACTION_DISMISS = "dismiss"
    ACTION_DELETE = "delete_message"
    ACTION_MUTE = "mute_handle"
    ACTION_EXPEL = "expel_handle"
    ACTION_REVEAL = "reveal_and_expel"
    ACTION_DELETE_AND_MUTE = "delete_and_mute"

    ACTION_CHOICES = [
        (ACTION_DISMISS, "Dismiss report"),
        (ACTION_DELETE, "Delete message"),
        (ACTION_MUTE, "Mute handle"),
        (ACTION_EXPEL, "Expel handle"),
        (ACTION_REVEAL, "Reveal identity and expel"),
        (ACTION_DELETE_AND_MUTE, "Delete message and mute handle"),
    ]

    action = forms.ChoiceField(choices=ACTION_CHOICES, widget=forms.Select(attrs={"class": "select"}))
    reason = forms.CharField(
        max_length=255,
        widget=forms.Textarea(attrs={"class": "textarea", "rows": 3}),
    )
