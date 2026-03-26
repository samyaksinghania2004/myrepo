from __future__ import annotations

from django import forms
from django.db.models import Q

from accounts.models import User

from .models import DiscussionRoom, Report, RoomInvite


class DiscussionRoomForm(forms.ModelForm):
    class Meta:
        model = DiscussionRoom
        fields = [
            "name",
            "description",
            "access_type",
            "is_archived",
        ]

    def __init__(self, *args, show_archive=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["access_type"].choices = [
            (DiscussionRoom.AccessType.PUBLIC, "Public"),
            (DiscussionRoom.AccessType.PRIVATE_INVITE_ONLY, "Private (invite only)"),
        ]
        if not show_archive:
            self.fields.pop("is_archived", None)


class JoinRoomForm(forms.Form):
    handle_name = forms.CharField(max_length=24)

    def __init__(self, *args, room=None, existing_handle=None, **kwargs):
        self.room = room
        self.existing_handle = existing_handle
        super().__init__(*args, **kwargs)

    def clean_handle_name(self):
        handle_name = self.cleaned_data["handle_name"].strip()
        if self.room:
            existing = self.room.room_handles.filter(handle_name__iexact=handle_name)
            if self.existing_handle:
                existing = existing.exclude(pk=self.existing_handle.pk)
            if existing.exists():
                raise forms.ValidationError("This handle is already taken in the room.")
        return handle_name


class RoomInviteForm(forms.Form):
    identifier = forms.CharField(
        max_length=150,
        label="Search by username or email",
        widget=forms.TextInput(
            attrs={
                "class": "input",
                "placeholder": "username or email",
                "data-user-search": "true",
            }
        ),
    )

    def __init__(self, *args, room=None, inviter=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.room = room
        self.inviter = inviter

    def clean(self):
        cleaned = super().clean()
        identifier = (cleaned.get("identifier") or "").strip()
        if not identifier:
            raise forms.ValidationError("Enter a username or email.")
        user = None
        if "@" in identifier:
            user = User.objects.filter(email__iexact=identifier).first()
            if user is None:
                matches = list(User.objects.filter(email__icontains=identifier)[:2])
                if len(matches) == 1:
                    user = matches[0]
                elif matches:
                    raise forms.ValidationError(
                        "Multiple users match. Use the full email address."
                    )
        else:
            user = User.objects.filter(username__iexact=identifier).first()
            if user is None:
                matches = list(
                    User.objects.filter(
                        Q(username__icontains=identifier)
                        | Q(first_name__icontains=identifier)
                        | Q(last_name__icontains=identifier)
                    )[:2]
                )
                if len(matches) == 1:
                    user = matches[0]
                elif matches:
                    raise forms.ValidationError(
                        "Multiple users match. Use the full username or email."
                    )
        if user is None:
            raise forms.ValidationError("User not found.")
        if self.inviter and getattr(self.inviter, "id", None) == user.id:
            raise forms.ValidationError("You cannot invite yourself.")
        if self.room:
            existing_ids = self.room.room_handles.filter(
                status__in=["approved", "pending"]
            ).values_list("user_id", flat=True)
            if user.id in set(existing_ids):
                raise forms.ValidationError("User is already in this room.")
        cleaned["recipient"] = user
        return cleaned


class MessageForm(forms.Form):
    text = forms.CharField(
        max_length=1000,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Share an update, ask a question, or start the discussion...",
            }
        ),
    )


class MessageEditForm(forms.Form):
    text = forms.CharField(max_length=1000, widget=forms.Textarea(attrs={"rows": 3}))


class ReportForm(forms.ModelForm):
    class Meta:
        model = Report
        fields = ["reason"]
        widgets = {
            "reason": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Why should this message be reviewed?",
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

    action = forms.ChoiceField(choices=ACTION_CHOICES)
    reason = forms.CharField(
        max_length=255,
        widget=forms.Textarea(
            attrs={"rows": 3, "placeholder": "Document why this moderation action is being taken."}
        ),
    )
