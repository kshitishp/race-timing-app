from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from accounts.models import MagicLink, Organisation, OrganisationMember, User


@admin.register(Organisation)
class OrganisationAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "billing_email", "created_at")
    search_fields = ("name", "slug", "billing_email")
    prepopulated_fields = {"slug": ("name",)}

    def has_module_permission(self, request):
        # Organisations are platform-level; only superusers manage tenants.
        return request.user.is_superuser

    has_view_permission = has_change_permission = has_delete_permission = (
        lambda self, request, obj=None: request.user.is_superuser
    )
    has_add_permission = lambda self, request: request.user.is_superuser


class OrganisationMemberInline(admin.TabularInline):
    model = OrganisationMember
    extra = 0


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Organiser staff *and* volunteers share this table (§8). An
    organiser needs to be able to create a new person here (to then
    assign them as a RaceVolunteer) even though Users aren't
    organisation-scoped by model design — so, like ProfileAdmin, this
    bypasses Django's permission-object framework (organisers are never
    granted explicit model permissions) and just checks organisation
    membership directly."""

    model = User
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("name", "phone")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "name", "password1", "password2")}),
    )
    list_display = ("email", "name", "phone", "is_staff", "is_active")
    search_fields = ("email", "name", "phone")
    ordering = ("email",)
    inlines = [OrganisationMemberInline]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        from accounts.tenancy import get_request_organisation

        organisation = get_request_organisation(request.user)
        if organisation is None:
            return qs.none()
        # An organiser can see: fellow organisation members + volunteers
        # assigned to any of this organisation's races.
        return qs.filter(
            models_q_organisation_or_volunteer(organisation)
        ).distinct()

    def _member_or_superuser(self, request):
        if request.user.is_superuser:
            return True
        from accounts.tenancy import get_request_organisation

        return get_request_organisation(request.user) is not None

    def has_module_permission(self, request):
        return self._member_or_superuser(request)

    def has_view_permission(self, request, obj=None):
        return self._member_or_superuser(request)

    def has_add_permission(self, request):
        return self._member_or_superuser(request)

    def has_change_permission(self, request, obj=None):
        return self._member_or_superuser(request)

    def get_inline_instances(self, request, obj=None):
        # OrganisationMember grants Django Admin access to a whole
        # organisation's data — an organiser managing a volunteer's User
        # record must not be able to grant that (to themselves or anyone
        # else, for this org or any other) via this inline. Only a
        # superuser sees/edits it.
        if not request.user.is_superuser:
            return []
        return super().get_inline_instances(request, obj)

    def get_fieldsets(self, request, obj=None):
        # Same reasoning as get_inline_instances: is_staff/is_superuser/
        # groups/user_permissions are platform-wide privilege grants, not
        # something an organiser editing a volunteer's basic details
        # should ever see, let alone toggle.
        if request.user.is_superuser:
            return super().get_fieldsets(request, obj)
        if obj is None:
            return self.add_fieldsets
        return (
            (None, {"fields": ("email", "password")}),
            ("Personal info", {"fields": ("name", "phone")}),
        )


def models_q_organisation_or_volunteer(organisation):
    from django.db.models import Q

    return Q(organisation_memberships__organisation=organisation) | Q(
        race_volunteer_assignments__race__organisation=organisation
    )


@admin.register(OrganisationMember)
class OrganisationMemberAdmin(admin.ModelAdmin):
    list_display = ("user", "organisation", "role")
    list_filter = ("role",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        from accounts.tenancy import get_request_organisation

        organisation = get_request_organisation(request.user)
        return qs.filter(organisation=organisation) if organisation else qs.none()

    def has_module_permission(self, request):
        if request.user.is_superuser:
            return True
        from accounts.tenancy import get_request_organisation

        return get_request_organisation(request.user) is not None


@admin.register(MagicLink)
class MagicLinkAdmin(admin.ModelAdmin):
    """Read-only — links are issued via the API, never hand-created."""

    list_display = ("user", "purpose", "race", "expires_at", "used_at", "created_at")
    list_filter = ("purpose",)
    search_fields = ("user__email",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs if request.user.is_superuser else qs.none()

    def has_module_permission(self, request):
        return request.user.is_superuser
