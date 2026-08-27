"""
Shared Django Admin scoping so an organiser only ever sees/edits their own
organisation's data (§6 confirmed decision: organiser CRUD is a
customized Django Admin, not a bespoke web app; §10: isolation enforced in
the application layer).

A platform superuser (created via createsuperuser) sees everything and is
used for platform operations / support, not by organisers.
"""

from accounts.models import Organisation
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

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # get_queryset/_object_allowed lock down the list/detail views,
        # but a plain ModelAdmin's add/change form otherwise still offers
        # every organisation's rows in FK dropdowns (e.g. Checkpoint's
        # `race` picker, or RaceVolunteer's `race`/`checkpoint` pickers) —
        # scope those too wherever the related model is itself
        # tenant-scoped. Models deliberately excluded from tenant scoping
        # (Profile, User) are left alone, matching their design intent.
        if not request.user.is_superuser:
            organisation = get_request_organisation(request.user)
            if organisation is not None:
                related_model = db_field.remote_field.model
                if related_model is Organisation:
                    kwargs["queryset"] = related_model.objects.filter(pk=organisation.pk)
                else:
                    tenant_path = getattr(related_model, "TENANT_FILTER_PATH", None)
                    if tenant_path:
                        kwargs["queryset"] = related_model.objects.filter(**{tenant_path: organisation})
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser and self.tenant_filter_path == "organisation":
            organisation = get_request_organisation(request.user)
            if organisation is not None and not getattr(obj, "organisation_id", None):
                obj.organisation = organisation
        super().save_model(request, obj, form, change)
