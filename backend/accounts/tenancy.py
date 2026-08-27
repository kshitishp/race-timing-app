"""
Tenant-isolation helpers (§10 Multi-Organiser & Tenancy Model).

MySQL doesn't give row-level security, so isolation is enforced in the
application layer: every organisation-scoped queryset must be filtered
through one of these helpers rather than hitting `Model.objects` directly
in views. `Profiles` is deliberately excluded — it's the one entity that's
intentionally not organisation-scoped (§10).
"""

from django.db import models


class OrganisationScopedQuerySet(models.QuerySet):
    """
    QuerySet for models with a direct or indirect path back to
    `Organisation`. Subclasses/models set `TENANT_FILTER_PATH` to the ORM
    lookup for that path, e.g. "organisation" on Race, or
    "race__organisation" on Checkpoint/Participant/RaceVolunteer, or
    "checkpoint__race__organisation" on Timing.
    """

    def for_organisation(self, organisation):
        path = self.model.TENANT_FILTER_PATH
        return self.filter(**{path: organisation})


class OrganisationScopedManager(models.Manager.from_queryset(OrganisationScopedQuerySet)):
    pass


def get_request_organisation(user):
    """
    Resolve the organisation an authenticated organiser-side request acts
    on. v0 assumes one organisation per organiser (see PRD §10 — co-admins
    are multiple users per organisation, not multiple organisations per
    user), so we use the user's first membership.
    """
    if not getattr(user, "is_authenticated", False):
        return None

    from accounts.models import OrganisationMember

    membership = (
        OrganisationMember.objects.select_related("organisation")
        .filter(user=user)
        .first()
    )
    if membership is None:
        return None
    return membership.organisation
