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


class ClubChannelForm(forms.Form):
    name = forms.CharField(max_length=80)
    is_private = forms.BooleanField(required=False, label="Private channel")

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError("Channel name cannot be empty.")
        return name


class ClubMessageForm(forms.Form):
    text = forms.CharField(
        max_length=2000,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Share an update, ask a question, or start the discussion...",
            }
        ),
    )


class ClubChannelMemberForm(forms.Form):
    identifier = forms.CharField(
        max_length=150,
        label="Add member by username or email",
        widget=forms.TextInput(
            attrs={
                "class": "input",
                "placeholder": "username or email",
                "data-user-search": "true",
            }
        ),
    )

    def __init__(self, *args, club=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.club = club

    def clean(self):
        cleaned = super().clean()
        identifier = (cleaned.get("identifier") or "").strip()
        if not identifier:
            raise forms.ValidationError("Enter a username or email address.")
        user_qs = User.objects.none()
        if "@" in identifier:
            user_qs = User.objects.filter(email__iexact=identifier)
        else:
            user_qs = User.objects.filter(username__iexact=identifier)
        user = user_qs.first()
        if user is None:
            user = User.objects.filter(email__iexact=identifier).first()
        if user is None:
            raise forms.ValidationError("User not found.")
        if self.club is None:
            raise forms.ValidationError("Club context is missing.")
        membership = ClubMembership.objects.filter(
            club=self.club,
            user=user,
            status=ClubMembership.Status.ACTIVE,
        ).first()
        if membership is None:
            raise forms.ValidationError("User must be an active club member.")
        cleaned["user"] = user
        return cleaned
