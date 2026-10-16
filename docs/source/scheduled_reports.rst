Scheduled reports
=================

Scheduled reports run an independent copy of a validated row or summary
report and email the complete bounded result to an explicitly confirmed list
of recipients. The feature is available from the **Scheduled reports** link in
the QBE builder or through Django Admin's **Django QBE 2** navigation.

A schedule belongs to the staff user who created it. Only that owner can view,
edit, pause, resume or delete it; superusers do not bypass this ownership rule.
The definition is copied when the schedule is created. Changing or deleting the
source saved query does not change the schedule. Use **Edit definition** and
explicitly update the snapshot to change what future runs execute.

.. warning::

   Email recipients receive report data as an attachment. They do not gain
   application access, and BCC hides recipient addresses from one another, but
   recipients can keep or forward the file. Confirm that every address is
   authorized to receive the report. Use the optional domain allowlist for an
   additional deployment-level restriction.

Create a schedule
-----------------

#. Build a row report or grouped summary and choose **Preview report**.
#. Choose **Schedule this report** from the results page.
#. Set a name, daily or weekly frequency, local time, IANA timezone, recipients
   and CSV or Excel format. Excel requires ``django-qbe2[excel]``.
#. Confirm that the listed recipients may receive the report, then save.

Addresses are entered one per line, normalized and deduplicated. The default
maximum is 10. The schedule screen shows its next run, last status and recent
sanitized run history. Recipients are not displayed in one another's messages.

Migration and storage
---------------------

After upgrading the package and adding ``django_qbe2`` to ``INSTALLED_APPS``,
apply its migrations:

.. code-block:: console

   python manage.py migrate

The package adds ``ScheduledReport`` and ``ScheduledReportRun`` tables to the
default database. User foreign keys use ``AUTH_USER_MODEL``. Schedules store a
bounded definition, recurrence, recipients and output format. Run history stores
only occurrence timestamps, status, attempts, a short lease and a sanitized
message. Report rows, SQL results and attachment contents are never persisted.

Run the scheduler
-----------------

The package does not start background threads or require Celery. Invoke this
bounded management command periodically through cron, a platform scheduler or
your task system:

.. code-block:: console

   python manage.py qbe2_run_scheduled_reports --limit 25

For example, a cron entry can poll once per minute:

.. code-block:: console

   * * * * * cd /srv/myproject && /srv/myproject/.venv/bin/python manage.py qbe2_run_scheduled_reports --limit 25

The database lease and unique schedule/occurrence record prevent two workers
from claiming the same occurrence. SQLite and PostgreSQL are supported. A worker
that exits without recording a result can be reclaimed after its 15-minute
lease expires. Failed runs retry after 5 and then 10 minutes, with at most three
attempts. A permission loss disables the schedule and requires owner review.

If the command is down for several periods, it sends only the most recent due
occurrence and moves to the next future occurrence; it does not send a burst of
missed reports. Pause stops new claims; an already claimed run can finish. Resume
chooses the next future local occurrence.

Delivery uses an at-least-once boundary: email delivery and saving the success
record cannot be one atomic transaction. If the process stops after the mail
server accepts a message but before the database records success, a retry may
send that same occurrence again. Keep the command supervised and monitor run
history for failed deliveries.

Email configuration
-------------------

Django QBE 2 sends a plain-text ``EmailMessage`` through the project's default
Django mailer. Configure that mailer for your deployment. For Django 6.0, use
the version's email settings, for example:

.. code-block:: python

   EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
   EMAIL_HOST = "smtp.example.com"
   EMAIL_PORT = 587
   EMAIL_HOST_USER = os.environ["SMTP_USERNAME"]
   EMAIL_HOST_PASSWORD = os.environ["SMTP_PASSWORD"]
   EMAIL_USE_TLS = True
   DEFAULT_FROM_EMAIL = "reports@example.com"

Django 6.1 introduces ``MAILERS``; configure the default mailer there instead
of relying on the deprecated ``EMAIL_*`` settings:

.. code-block:: python

   MAILERS = {
       "default": {
           "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
           "OPTIONS": {
               "host": "smtp.example.com",
               "port": 587,
               "username": os.environ["SMTP_USERNAME"],
               "password": os.environ["SMTP_PASSWORD"],
               "use_tls": True,
               "timeout": 10,
           },
       },
   }
   DEFAULT_FROM_EMAIL = "reports@example.com"

For a safe local run, configure Django's console email backend; it prints the
message without contacting an external service. Django's test runner uses the
in-memory backend automatically. QBE does not require an SMTP or email-provider
package of its own. See Django's `email documentation <https://docs.djangoproject.com/en/6.1/topics/email/>`_
and `MAILERS settings <https://docs.djangoproject.com/en/6.1/ref/settings/#mailers>`_.

Recurrence and timezone behavior
--------------------------------

Schedules run daily or weekly at minute precision in the saved IANA timezone.
The database stores the next occurrence in UTC. During a daylight-saving gap,
the occurrence moves to the first valid local minute after the gap. During a
repeated hour, it uses the first occurrence. These rules keep the local schedule
predictable while avoiding skipped or duplicate runs at a clock transition.

Authorization and output limits
-------------------------------

Each occurrence loads the owner again, rebuilds the authorized report catalog,
validates the stored definition and executes the report's current
``get_queryset(request)`` policy. Related report permissions and row policies
are checked through the same report engine. A superuser running the management
command never replaces the schedule owner. If the report, required fields,
owner's active/staff state or required permissions are no longer valid, the run
fails without sending an attachment and disables the schedule for review.

Reports that need middleware-added request context, such as a tenant, can
provide it on their ``Report`` class:

.. code-block:: python

   class OrderReport(Report):
       model = Order
       fields = ("number", "total")

       def get_queryset(self, request):
           return Order.objects.filter(tenant=request.tenant)

       def get_scheduled_request(self, *, owner, schedule):
           request = super().get_scheduled_request(owner=owner, schedule=schedule)
           request.tenant = tenant_for_schedule_owner(owner)
           return request

The hook must return an ``HttpRequest`` whose ``user`` is the schedule owner.
QBE restores the fresh database-loaded owner after calling the hook. If a report
cannot reconstruct its required context, its policy should fail closed. The
schedule timezone is available as ``request.timezone``.

Each export must be complete. Existing limits cap report rows, summary source
rows, summary output rows and related values. A schedule fails without an
attachment if any applicable limit is exceeded. Attachments are capped at 10 MiB
by default, configurable with ``QBE2_MAX_SCHEDULED_ATTACHMENT_BYTES``. Recipient
count defaults to 10 and can be changed with ``QBE2_MAX_SCHEDULED_RECIPIENTS``.
Optionally set ``QBE2_SCHEDULED_EMAIL_DOMAIN_ALLOWLIST`` to a list or tuple of
accepted domains. See :doc:`configuration` for the complete settings table.

Troubleshooting
---------------

- **No email was sent:** inspect the schedule's last-run status and the host
  project's configured mailer; run the management command manually to see its
  batch summary.
- **The schedule was disabled:** restore the owner's active staff status,
  report-level view permissions and any related-report permissions, then review
  the definition and resume it.
- **The report exceeded a limit:** narrow its conditions, reduce selected
  related values or groups, or adjust the relevant positive integer QBE limit.
  The package will not send a partial attachment.
- **A recipient domain is rejected:** check
  ``QBE2_SCHEDULED_EMAIL_DOMAIN_ALLOWLIST`` in the settings module used by the
  command process.
- **No run is due:** check the stored timezone and next-run time; the command
  only processes due schedules and should be invoked periodically.
