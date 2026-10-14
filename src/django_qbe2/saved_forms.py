from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _


class SavedQueryNameForm(forms.Form):
    name = forms.CharField(label=_("Name"), max_length=120)


class SavedQuerySettingsForm(SavedQueryNameForm):
    shared_with = forms.CharField(
        label=_("Share with"),
        required=False,
        max_length=8000,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text=_(
            "Enter known staff login identifiers, one per line (up to 50). "
            "Leave empty for a private query. Recipients can read and save a copy."
        ),
    )

    def __init__(self, *args, owner, **kwargs):
        super().__init__(*args, **kwargs)
        self.owner = owner

    def clean_shared_with(self):
        identifiers = set(self.cleaned_data["shared_with"].splitlines())
        identifiers = {value.strip() for value in identifiers if value.strip()}
        if len(identifiers) > 50:
            raise forms.ValidationError(_("Share with at most 50 users."))
        model = get_user_model()
        users = list(
            model._default_manager.filter(
                is_active=True,
                is_staff=True,
                **{f"{model.USERNAME_FIELD}__in": identifiers},
            )
        )
        found = {str(user.get_username()) for user in users}
        if identifiers != found:
            raise forms.ValidationError(
                _("Use an active staff user's login identifier on each line.")
            )
        return [user for user in users if user.pk != self.owner.pk]
