Reports and permissions
=======================

Explicit registration
---------------------

Import :py:class:`django_qbe2.registry.Report` and
:py:func:`django_qbe2.registry.register` in your installed app's ``qbe.py``.
Declare a Django model, a nonempty tuple of permitted field paths and a mandatory
``get_queryset(request)`` method. Optional ``field_labels`` map only declared paths
to display text. A model may be registered once; duplicates raise
``ImproperlyConfigured`` during startup.

Do not read database rows while importing the module. Report instances are shared
configuration: do not store a request, a user, evaluated rows or request-specific
querysets on them. The permission catalog is rebuilt for each request.

Three authorization boundaries
------------------------------

#. Entry requires an authenticated, active staff user.
#. A root report requires Django's ``<app_label>.view_<model_name>`` permission.
   A related field also requires the target model's view permission.
#. Each root and target report supplies its own authorized rows through
   ``get_queryset(request)``. Django model permissions do not imply row access.

Staff status alone does not grant report access. The package does not infer
ownership or tenant rules, and it does not automatically reuse a ModelAdmin's row
policy. Call an existing shared policy if your application already defines one.
Superusers bypass model permission checks through Django's normal behavior but
still follow the report's row policy. An explicit all-rows policy is your choice.

For the example's owner-based model, an explicit policy can grant superusers all
rows and scope other staff to their own rows:

.. code-block:: python

   def get_queryset(self, request):
       queryset = self.model.objects.all()
       if request.user.is_superuser:
           return queryset
       return queryset.filter(owner=request.user)

Choose this policy only when your application authorizes that access. ``owner``
is the example model's field; QBE does not require that name or infer ownership.

The :doc:`installation` example uses owner equality. In a tenant application,
return the tenant-scoped queryset your authenticated request is authorized to read.
Never accept a client-provided tenant ID as authorization by itself.

QuerySet contract
-----------------

Return an unevaluated QuerySet of the declared model on the **default database**.
Do not return a list, a slice, or a ``values()``/``values_list()`` projection. The
engine applies authorized conditions, ordering, projection and report limits later.
An invalid policy return raises a configuration error.

Relationship paths
------------------

Paths may traverse up to two registered ForeignKey, OneToOne or ManyToMany
relationships in either direction, for example ``customer__name`` or
``customer__pets__name``. Generic relations are unsupported. A field path may
contain at most one multi-valued edge. Forward ForeignKey ``to_field`` uses the
referenced target key.

Each report along the path must be visible to the user and its
``get_queryset(request)`` policy scopes the related objects. This applies to HTML,
CSV, saved queries and shared queries. Multi-valued paths can be selected and
filtered, but cannot be used for row ordering, summary grouping or numeric summary
metrics. See :doc:`relationship-design` for collection formatting, existential
filter behavior and the related-value limit.
