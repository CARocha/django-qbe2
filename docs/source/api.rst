Public registration API
=======================

The supported configuration surface is ``django_qbe2.registry`` plus Django
settings and namespaced URLs. Internal catalog, validation, engine and form helpers
are implementation details; importing them does not establish a stable public API.
The package is experimental, so follow release notes before upgrading.

.. py:module:: django_qbe2.registry

.. py:class:: Report

   Abstract base class for a registered Django model report.

   .. py:attribute:: model

      Django model class. Required, not an instance or a model name string.

   .. py:attribute:: fields

      Nonempty tuple of unique scalar field paths. Local paths or one forward
      FK/OneToOne hop are supported. Default: empty tuple.

   .. py:attribute:: field_labels

      Optional dictionary mapping declared field paths to display text.
      Default: empty dictionary. Do not mutate shared configuration per request.

   .. py:method:: get_queryset(request)

      Required row authorization policy. Return an unsliced, unprojected QuerySet
      of ``model`` on the default database for this authenticated request. No
      implicit owner or tenant policy is supplied. See :doc:`reports`.

.. py:function:: register(report_class)

   Decorator registering a Report subclass. Returns the class unchanged so it can
   still be referenced normally. Creates its shared configuration instance and
   identifies it by ``model._meta.label_lower`` (for example ``sales.order``).

   Raises Django ``ImproperlyConfigured`` for a non-Report class, invalid model,
   missing policy implementation or duplicate model registration. The class is
   constructed without arguments; declare configuration as class attributes.

.. py:function:: get_reports()

   Return a tuple of registered Report instances in registration order.
   This is configuration introspection, **not an authorized catalog**. Never expose
   it directly to an untrusted user or assume it applies permissions. Request-level
   visibility and row policies are enforced by the app's views.

See the :doc:`installation` example for complete runnable declarations and
:doc:`configuration` for settings and HTTP route names.
