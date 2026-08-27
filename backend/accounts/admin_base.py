"""
Shared Django Admin scoping so an organiser only ever sees/edits their own
organisation's data (§6 confirmed decision: organiser CRUD is a
customized Django Admin, not a bespoke web app; §10: isolation enforced in
the application layer).

A platform superuser (created via createsuperuser) sees everything and is
used for platform operations / support, not by organisers.
"""

from accounts.tenancy import get_request_organisation


class OrganisationScopedAdminMixin:
    """Mix into a ModelAdmin for a model whose manager is an
    OrganisationScopedManager (or the model itself is Organisation)."""

    # ORM lookup path from this model back to Organisation, e.g.
    # "organisation" (Race) or "race__organisation" (Checkpoint).
    tenant_filter_path = "organisation"

    def _user_organisation(self, request):
        if request.user.is_superuser:
            return None  # signals "no filtering"
        return get_request_organisation(request.user)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        organisation = get_request_organisation(request.user)
        if organisation is None:
            return qs.none()
        return qs.filter(**{self.tenant_filter_path: organisation})

    def has_module_permission(self, request):
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return get_request_organisation(request.user) is not None

    def has_view_permission(self, request, obj=None):
        return self._object_allowed(request, obj)

    def has_change_permission(self, request, obj=None):
        return self._object_allowed(request, obj)

    def has_delete_permission(self, request, obj=None):
        return self._object_allowed(request, obj)

    def has_add_permission(self, request):
        if request.user.is_superuser:
            return True
        return get_request_organisation(request.user) is not None

    def _object_allowed(self, request, obj):
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        organisation = get_request_organisation(request.user)
        if organisation is None:
            return False
        if obj is None:
            return True
        obj_org = obj
        for step in self.tenant_filter_path.split("__"):
            obj_org = getattr(obj_org, step, None)
            if obj_org is None:
                return False
        return obj_org.pk == organisation.pk

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser and self.tenant_filter_path == "organisation":
            organisation = get_request_organisation(request.user)
            if organisation is not None and not getattr(obj, "organisation_id", None):
                obj.organisation = organisation
        super().save_model(request, obj, form, change)
