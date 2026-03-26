from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model
from django.db import models


class SearchForm(forms.Form):
    q = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "input",
                "placeholder": "Search clubs, events, rooms",
                "maxlength": 50,
            }
        ),
        label="Search",
    )


class DirectMessageStartForm(forms.Form):
    identifier = forms.CharField(
        max_length=150,
        label="Message someone",
        widget=forms.TextInput(
            attrs={
                "class": "input",
                "placeholder": "username or email",
                "data-user-search": "true",
            }
        ),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean(self):
        cleaned = super().clean()
        identifier = (cleaned.get("identifier") or "").strip()
        if not identifier:
            raise forms.ValidationError("Enter a username or email address.")
        User = get_user_model()
        qs = User.objects.filter(is_active=True)
        if "@" in identifier:
            qs = qs.filter(email__iexact=identifier)
        else:
            qs = qs.filter(username__iexact=identifier)
        user = qs.first()
        if user is None:
            user = User.objects.filter(
                is_active=True
            ).filter(
                models.Q(username__icontains=identifier)
                | models.Q(email__icontains=identifier)
            ).order_by("username").first()
        if user is None:
            raise forms.ValidationError("User not found.")
        if self.user and user.id == self.user.id:
            raise forms.ValidationError("Pick someone else to message.")
        cleaned["recipient"] = user
        return cleaned


class DirectMessageForm(forms.Form):
    body = forms.CharField(
        max_length=2000,
        widget=forms.Textarea(
            attrs={
                "rows": 2,
                "placeholder": "Write a message...",
            }
        ),
    )
