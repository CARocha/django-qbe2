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
