from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django import forms
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.validators import validate_email
from django.utils.translation import gettext_lazy as _

from django_qbe2.exports import excel_available
from django_qbe2.limits import get_limits
from django_qbe2.models import ScheduledReport


class ScheduledReportForm(forms.Form):
    name = forms.CharField(label=_("Name"), max_length=120)
    frequency = forms.ChoiceField(
        label=_("Frequency"), choices=ScheduledReport.Frequency.choices
    )
    weekday = forms.ChoiceField(
        label=_("Day of week"),
        choices=[
            ("", "---------"),
            ("0", _("Monday")),
            ("1", _("Tuesday")),
            ("2", _("Wednesday")),
            ("3", _("Thursday")),
            ("4", _("Friday")),
            ("5", _("Saturday")),
            ("6", _("Sunday")),
        ],
        required=False,
    )
    local_time = forms.TimeField(
        label=_("Local time"),
        widget=forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
    )
    timezone = forms.CharField(
        label=_("Time zone"),
        max_length=64,
        help_text=_("Use an IANA time zone, such as Europe/Madrid."),
    )
    recipients = forms.CharField(
        label=_("Email recipients"),
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text=_("Enter one email address per line. Addresses are sent privately."),
    )
    format = forms.ChoiceField(
        label=_("Attachment format"), choices=ScheduledReport.OutputFormat.choices
    )
    confirm_recipients = forms.BooleanField(
        label=_("I confirm these recipients are authorized to receive this report."),
        required=True,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not excel_available():
            self.fields["format"].choices = [
                choice
                for choice in ScheduledReport.OutputFormat.choices
                if choice[0] == ScheduledReport.OutputFormat.CSV
            ]

    def clean_timezone(self):
        value = self.cleaned_data["timezone"].strip()
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise forms.ValidationError(_("Choose a valid IANA time zone.")) from error
        return value

    def clean_recipients(self):
        lines = self.cleaned_data["recipients"].splitlines()
        recipients = []
        seen = set()
        for line in lines:
            address = line.strip()
            if not address:
                continue
            try:
                validate_email(address)
            except forms.ValidationError as error:
                raise forms.ValidationError(
                    _("Enter one valid email address per line.")
                ) from error
            local, domain = address.rsplit("@", 1)
            normalized = f"{local}@{domain.lower()}"
            key = normalized.casefold()
            if key not in seen:
                seen.add(key)
                recipients.append(normalized)

        if not recipients:
            raise forms.ValidationError(_("Enter at least one email recipient."))
        maximum = get_limits().max_scheduled_recipients
        if len(recipients) > maximum:
            raise forms.ValidationError(
                _("Enter no more than %(maximum)s email recipients.")
                % {"maximum": maximum}
            )

        allowed_domains = getattr(settings, "QBE2_SCHEDULED_EMAIL_DOMAIN_ALLOWLIST", ())
        if allowed_domains is None:
            allowed_domains = ()
        if not isinstance(allowed_domains, (list, tuple)) or any(
            not isinstance(domain, str) or not domain.strip()
            for domain in allowed_domains
        ):
            raise ImproperlyConfigured(
                "QBE2_SCHEDULED_EMAIL_DOMAIN_ALLOWLIST must be a list or tuple "
                "of domains."
            )
        allowed = {domain.strip().lower() for domain in allowed_domains}
        if allowed and any(
            recipient.rsplit("@", 1)[1].lower() not in allowed
            for recipient in recipients
        ):
            raise forms.ValidationError(
                _("One or more recipient email domains are not allowed.")
            )
        return recipients

    def clean_format(self):
        value = self.cleaned_data["format"]
        if value == ScheduledReport.OutputFormat.XLSX and not excel_available():
            raise forms.ValidationError(
                _("Install django-qbe2[excel] to schedule Excel attachments.")
            )
        return value

    def clean(self):
        cleaned_data = super().clean()
        frequency = cleaned_data.get("frequency")
        weekday = cleaned_data.get("weekday")
        if frequency == ScheduledReport.Frequency.WEEKLY:
            if not weekday:
                self.add_error("weekday", _("Choose a day for weekly reports."))
            else:
                cleaned_data["weekday"] = int(weekday)
        elif frequency == ScheduledReport.Frequency.DAILY:
            if weekday:
                self.add_error("weekday", _("Daily reports do not use a weekday."))
            cleaned_data["weekday"] = None
        return cleaned_data
