from __future__ import annotations

from django import forms

from clubs_events.models import Club, Event
from accounts.models import User

from .models import DiscussionRoom, Report, RoomInvite


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
            "is_archived",
        ]

    def __init__(self, *args, club_queryset=None, event_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["club"].queryset = club_queryset or Club.objects.filter(is_active=True)
        self.fields["event"].queryset = event_queryset or Event.objects.filter(is_archived=False)


class JoinRoomForm(forms.Form):
    handle_name = forms.CharField(max_length=24)

    def __init__(self, *args, room=None, **kwargs):
        self.room = room
        super().__init__(*args, **kwargs)

    def clean_handle_name(self):
        handle_name = self.cleaned_data["handle_name"].strip()
        if self.room and self.room.room_handles.filter(handle_name__iexact=handle_name).exists():
            raise forms.ValidationError("This handle is already taken in the room.")
        return handle_name


class RoomInviteForm(forms.Form):
    recipient = forms.ModelChoiceField(queryset=User.objects.none())

    def __init__(self, *args, room=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.room = room
        qs = User.objects.all()
        if room and room.club:
            member_ids = room.club.memberships.filter(status="active").values_list("user_id", flat=True)
            qs = qs.filter(id__in=member_ids)
        if room and room.event:
            attendee_ids = room.event.registrations.filter(status="registered").values_list("user_id", flat=True)
            qs = qs.filter(id__in=attendee_ids)
        self.fields["recipient"].queryset = qs


class MessageForm(forms.Form):
    text = forms.CharField(max_length=1000, widget=forms.Textarea(attrs={"rows": 3}))


class MessageEditForm(forms.Form):
    text = forms.CharField(max_length=1000, widget=forms.Textarea(attrs={"rows": 3}))


class ReportForm(forms.ModelForm):
    class Meta:
        model = Report
        fields = ["reason"]


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

    action = forms.ChoiceField(choices=ACTION_CHOICES)
    reason = forms.CharField(max_length=255, widget=forms.Textarea(attrs={"rows": 3}))
