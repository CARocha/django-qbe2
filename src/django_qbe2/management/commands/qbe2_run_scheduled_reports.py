"""Run a bounded batch of due QBE reports and email their attachments."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.translation import gettext as _

from django_qbe2.scheduled_execution import prepare_scheduled_execution
from django_qbe2.scheduled_exports import build_report_attachment, send_scheduled_report
from django_qbe2.scheduling import claim_due_runs, finish_scheduled_run


class Command(BaseCommand):
    help = "Run a bounded batch of due scheduled QBE reports."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=25)

    def handle(self, *args, **options):
        limit = options["limit"]
        if limit < 1:
            raise CommandError("--limit must be a positive integer.")
        runs = claim_due_runs(now=timezone.now(), limit=limit)
        succeeded = 0
        failed = 0
        for run in runs:
            try:
                execution = prepare_scheduled_execution(run.schedule)
                attachment = build_report_attachment(execution, run.schedule)
                send_scheduled_report(run.schedule, attachment)
            except PermissionDenied:
                run.schedule.enabled = False
                run.schedule.save(update_fields=("enabled", "updated_at"))
                finish_scheduled_run(
                    run,
                    now=timezone.now(),
                    error_summary=(
                        "Report access changed; review the owner's permissions."
                    ),
                    retryable=False,
                )
                failed += 1
            except ValidationError:
                finish_scheduled_run(
                    run,
                    now=timezone.now(),
                    error_summary="Review the report definition and output limits.",
                )
                failed += 1
            except Exception:
                finish_scheduled_run(
                    run,
                    now=timezone.now(),
                    error_summary=(
                        "Report delivery failed; check the configured mailer."
                    ),
                )
                failed += 1
            else:
                finish_scheduled_run(run, now=timezone.now())
                succeeded += 1
        self.stdout.write(
            _(
                "Processed %(processed)s scheduled reports: %(succeeded)s "
                "succeeded, %(failed)s failed."
            )
            % {"processed": len(runs), "succeeded": succeeded, "failed": failed}
        )
