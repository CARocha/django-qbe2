from uuid import uuid4

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class SavedQuery(models.Model):
    """A reusable definition; ownership and sharing never grant data access."""

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="qbe2_owned_queries",
    )
    shared_with = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="qbe2_shared_queries"
    )
    name = models.CharField(_("Name"), max_length=120)
    definition = models.JSONField()
    page_size = models.PositiveSmallIntegerField(default=50)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at", "id")
        default_permissions = ()
        verbose_name = _("saved query")
        verbose_name_plural = _("saved queries")

    def __str__(self):
        return self.name


class ScheduledReport(models.Model):
    """Owner-controlled snapshot and recurrence for a bounded report."""

    class Frequency(models.TextChoices):
        DAILY = "daily", _("Daily")
        WEEKLY = "weekly", _("Weekly")

    class OutputFormat(models.TextChoices):
        CSV = "csv", _("CSV")
        XLSX = "xlsx", _("Excel")

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="qbe2_owned_scheduled_reports",
    )
    name = models.CharField(_("Name"), max_length=120)
    definition = models.JSONField()
    page_size = models.PositiveSmallIntegerField(default=50)
    frequency = models.CharField(max_length=8, choices=Frequency.choices)
    weekday = models.PositiveSmallIntegerField(null=True, blank=True)
    local_time = models.TimeField()
    timezone = models.CharField(max_length=64)
    recipients = models.JSONField(default=list)
    format = models.CharField(
        max_length=4, choices=OutputFormat.choices, default=OutputFormat.CSV
    )
    enabled = models.BooleanField(default=True)
    next_run_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("next_run_at", "id")
        default_permissions = ()
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(frequency="daily", weekday__isnull=True)
                    | models.Q(frequency="weekly", weekday__gte=0, weekday__lte=6)
                ),
                name="qbe2_schedule_weekday_matches_frequency",
            )
        ]
        indexes = [models.Index(fields=("enabled", "next_run_at"))]
        verbose_name = _("scheduled report")
        verbose_name_plural = _("scheduled reports")

    def __str__(self):
        return self.name


class ScheduledReportRun(models.Model):
    """Bounded status for one scheduled occurrence; never stores report data."""

    class Status(models.TextChoices):
        QUEUED = "queued", _("Queued")
        RUNNING = "running", _("Running")
        SUCCEEDED = "succeeded", _("Succeeded")
        FAILED = "failed", _("Failed")

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    schedule = models.ForeignKey(
        ScheduledReport,
        on_delete=models.CASCADE,
        related_name="runs",
    )
    scheduled_for = models.DateTimeField()
    status = models.CharField(max_length=9, choices=Status.choices)
    attempts = models.PositiveSmallIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    error_summary = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-scheduled_for", "id")
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(
                fields=("schedule", "scheduled_for"),
                name="qbe2_unique_scheduled_occurrence",
            ),
            models.CheckConstraint(
                condition=models.Q(attempts__lte=3),
                name="qbe2_scheduled_attempts_bounded",
            ),
        ]
        indexes = [
            models.Index(fields=("status", "lease_expires_at")),
        ]
        verbose_name = _("scheduled report run")
        verbose_name_plural = _("scheduled report runs")

    def __str__(self):
        return f"{self.schedule.name} — {self.scheduled_for:%Y-%m-%d %H:%M UTC}"
