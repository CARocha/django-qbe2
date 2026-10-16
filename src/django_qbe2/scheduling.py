from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


def _is_valid_local_time(candidate: datetime, timezone: ZoneInfo) -> bool:
    localized = candidate.replace(tzinfo=timezone, fold=0)
    round_trip = localized.astimezone(UTC).astimezone(timezone)
    return round_trip.replace(tzinfo=None) == candidate


def _resolve_local_time(candidate: datetime, timezone: ZoneInfo) -> datetime:
    if _is_valid_local_time(candidate, timezone):
        return candidate.replace(tzinfo=timezone, fold=0)

    for minutes in range(1, 24 * 60 + 1):
        after_gap = candidate + timedelta(minutes=minutes)
        if _is_valid_local_time(after_gap, timezone):
            return after_gap.replace(tzinfo=timezone, fold=0)

    raise ValidationError(
        _("Could not resolve this local time in the selected time zone.")
    )


def next_run_at(
    *,
    frequency: str,
    local_time: time,
    timezone_name: str,
    weekday: int | None,
    after: datetime,
) -> datetime:
    """Return the next daily or weekly occurrence as an aware UTC datetime."""
    if frequency not in {"daily", "weekly"}:
        raise ValidationError(_("Choose a daily or weekly frequency."))
    if not isinstance(local_time, time) or local_time.tzinfo is not None:
        raise ValidationError(_("Choose a local time without a time zone."))
    if local_time.second or local_time.microsecond:
        raise ValidationError(_("Scheduled local times must use whole minutes."))
    if not isinstance(timezone_name, str) or not timezone_name:
        raise ValidationError(_("Choose a valid IANA time zone."))
    try:
        timezone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ValidationError(_("Choose a valid IANA time zone.")) from error
    if (
        not isinstance(after, datetime)
        or after.tzinfo is None
        or after.utcoffset() is None
    ):
        raise ValidationError(_("The reference time must include a time zone."))
    if frequency == "weekly":
        if type(weekday) is not int or not 0 <= weekday <= 6:
            raise ValidationError(_("Choose a weekday from Monday to Sunday."))
    elif weekday is not None:
        raise ValidationError(_("Daily schedules do not use a weekday."))

    after_utc = after.astimezone(UTC)
    local_date = after_utc.astimezone(timezone).date()
    for offset in range(8):
        candidate_date = local_date + timedelta(days=offset)
        if frequency == "weekly" and candidate_date.weekday() != weekday:
            continue
        candidate = datetime.combine(candidate_date, local_time)
        occurrence = _resolve_local_time(candidate, timezone).astimezone(UTC)
        if occurrence > after_utc:
            return occurrence

    raise ValidationError(_("Could not determine the next scheduled occurrence."))


def retry_at(*, attempt: int, after: datetime) -> datetime | None:
    """Return bounded exponential retry time, or None after the final attempt."""
    if type(attempt) is not int or attempt < 1:
        raise ValidationError(_("Attempt must be a positive integer."))
    if (
        not isinstance(after, datetime)
        or after.tzinfo is None
        or after.utcoffset() is None
    ):
        raise ValidationError(_("The retry time must include a time zone."))
    if attempt >= 3:
        return None
    delay_minutes = min(60, 5 * 2 ** (attempt - 1))
    return after.astimezone(UTC) + timedelta(minutes=delay_minutes)


def _retry_sqlite_locked(operation):
    from time import sleep

    from django.db import OperationalError, connections

    for attempt in range(4):
        try:
            return operation()
        except OperationalError as error:
            if (
                connections["default"].vendor != "sqlite"
                or "locked" not in str(error).casefold()
                or attempt == 3
            ):
                raise
            sleep(0.01 * (attempt + 1))


def latest_due_occurrence(*, schedule, now: datetime) -> datetime:
    """Return the newest recurrence at or before now, skipping missed runs."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValidationError(_("The current time must include a time zone."))
    zone = ZoneInfo(schedule.timezone)
    now_utc = now.astimezone(UTC)
    local_date = now_utc.astimezone(zone).date()
    for days_back in range(8):
        candidate_date = local_date - timedelta(days=days_back)
        if (
            schedule.frequency == "weekly"
            and candidate_date.weekday() != schedule.weekday
        ):
            continue
        candidate = datetime.combine(candidate_date, schedule.local_time)
        occurrence = _resolve_local_time(candidate, zone).astimezone(UTC)
        if occurrence <= now_utc:
            return occurrence
    raise ValidationError(_("Could not determine the latest scheduled occurrence."))


def claim_due_runs(*, now: datetime, limit: int):
    """Claim at most ``limit`` due or retrying occurrences with database leases."""
    from django.db import IntegrityError, OperationalError, connections, transaction
    from django.db.models import F

    from django_qbe2.models import ScheduledReport, ScheduledReportRun

    if type(limit) is not int or limit < 1:
        raise ValidationError(_("The run limit must be a positive integer."))
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValidationError(_("The current time must include a time zone."))
    now = now.astimezone(UTC)
    lease_until = now + timedelta(minutes=15)
    claimed = []

    retry_ids = _retry_sqlite_locked(
        lambda: list(
            ScheduledReportRun.objects.filter(
                status=ScheduledReportRun.Status.FAILED,
                attempts__lt=3,
                lease_expires_at__lte=now,
                schedule__enabled=True,
            )
            .order_by("lease_expires_at", "scheduled_for")
            .values_list("pk", flat=True)[:limit]
        )
    )
    for run_id in retry_ids:
        run = _retry_sqlite_locked(
            lambda run_id=run_id: _claim_existing_run(
                run_id=run_id,
                now=now,
                lease_until=lease_until,
                status=ScheduledReportRun.Status.FAILED,
                run_model=ScheduledReportRun,
                transaction=transaction,
                increment=F("attempts") + 1,
            )
        )
        if run is not None:
            claimed.append(run)
    if len(claimed) >= limit:
        return claimed

    expired_final_runs = ScheduledReportRun.objects.filter(
        status=ScheduledReportRun.Status.RUNNING,
        attempts__gte=3,
        lease_expires_at__lte=now,
    )
    if _retry_sqlite_locked(expired_final_runs.exists):
        try:
            _retry_sqlite_locked(
                lambda: expired_final_runs.update(
                    status=ScheduledReportRun.Status.FAILED,
                    finished_at=now,
                    lease_expires_at=None,
                    error_summary="The run lease expired after the final attempt.",
                )
            )
        except OperationalError as error:
            if (
                connections["default"].vendor != "sqlite"
                or "locked" not in str(error).casefold()
            ):
                raise

    stale_ids = _retry_sqlite_locked(
        lambda: list(
            ScheduledReportRun.objects.filter(
                status=ScheduledReportRun.Status.RUNNING,
                attempts__lt=3,
                lease_expires_at__lte=now,
                schedule__enabled=True,
            )
            .order_by("lease_expires_at", "scheduled_for")
            .values_list("pk", flat=True)[: limit - len(claimed)]
        )
    )
    for run_id in stale_ids:
        run = _retry_sqlite_locked(
            lambda run_id=run_id: _claim_existing_run(
                run_id=run_id,
                now=now,
                lease_until=lease_until,
                status=ScheduledReportRun.Status.RUNNING,
                run_model=ScheduledReportRun,
                transaction=transaction,
                increment=F("attempts") + 1,
            )
        )
        if run is not None:
            claimed.append(run)
    if len(claimed) >= limit:
        return claimed

    due_ids = _retry_sqlite_locked(
        lambda: list(
            ScheduledReport.objects.filter(enabled=True, next_run_at__lte=now)
            .order_by("next_run_at", "pk")
            .values_list("pk", flat=True)[: limit - len(claimed)]
        )
    )
    for schedule_id in due_ids:
        try:
            run = _retry_sqlite_locked(
                lambda schedule_id=schedule_id: _claim_due_schedule(
                    schedule_id=schedule_id,
                    now=now,
                    lease_until=lease_until,
                    schedule_model=ScheduledReport,
                    run_model=ScheduledReportRun,
                    transaction=transaction,
                )
            )
        except IntegrityError:
            continue
        if run is not None:
            claimed.append(run)
    return claimed[:limit]


def _claim_existing_run(
    *, run_id, now, lease_until, status, run_model, transaction, increment
):
    from django_qbe2.models import ScheduledReportRun

    with transaction.atomic():
        run = (
            run_model.objects.select_for_update()
            .filter(
                pk=run_id,
                status=status,
                attempts__lt=3,
                lease_expires_at__lte=now,
                schedule__enabled=True,
            )
            .first()
        )
        if run is None:
            return None
        updated = run_model.objects.filter(
            pk=run.pk,
            status=status,
            attempts=run.attempts,
            lease_expires_at=run.lease_expires_at,
            schedule__enabled=True,
        ).update(
            status=ScheduledReportRun.Status.RUNNING,
            attempts=increment,
            started_at=now,
            finished_at=None,
            lease_expires_at=lease_until,
        )
        return run_model.objects.get(pk=run.pk) if updated else None


def _claim_due_schedule(
    *, schedule_id, now, lease_until, schedule_model, run_model, transaction
):
    from django_qbe2.models import ScheduledReportRun

    with transaction.atomic():
        schedule = (
            schedule_model.objects.select_for_update()
            .filter(pk=schedule_id, enabled=True, next_run_at__lte=now)
            .first()
        )
        if schedule is None:
            return None
        occurrence = latest_due_occurrence(schedule=schedule, now=now)
        if run_model.objects.filter(
            schedule=schedule, scheduled_for=occurrence
        ).exists():
            return None
        next_occurrence = next_run_at(
            frequency=schedule.frequency,
            weekday=schedule.weekday,
            local_time=schedule.local_time,
            timezone_name=schedule.timezone,
            after=now,
        )
        updated = schedule_model.objects.filter(
            pk=schedule.pk,
            enabled=True,
            next_run_at=schedule.next_run_at,
        ).update(next_run_at=next_occurrence)
        if not updated:
            return None
        return run_model.objects.create(
            schedule=schedule,
            scheduled_for=occurrence,
            status=ScheduledReportRun.Status.RUNNING,
            attempts=1,
            started_at=now,
            lease_expires_at=lease_until,
        )


def finish_scheduled_run(
    run, *, now: datetime, error_summary: str | None = None, retryable: bool = True
) -> None:
    from django_qbe2.models import ScheduledReportRun

    if now.tzinfo is None or now.utcoffset() is None:
        raise ValidationError(_("The finish time must include a time zone."))
    run.finished_at = now.astimezone(UTC)
    if error_summary:
        run.status = ScheduledReportRun.Status.FAILED
        run.error_summary = error_summary[:500]
        run.lease_expires_at = (
            retry_at(attempt=run.attempts, after=now) if retryable else None
        )
    else:
        run.status = ScheduledReportRun.Status.SUCCEEDED
        run.error_summary = ""
        run.lease_expires_at = None
    run.save(
        update_fields=("status", "error_summary", "finished_at", "lease_expires_at")
    )
