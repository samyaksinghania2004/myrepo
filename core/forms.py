from __future__ import annotations

from django import forms


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
