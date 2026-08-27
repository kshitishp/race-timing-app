from django.contrib import admin, messages

from import_export.admin import ImportExportModelAdmin

from accounts.admin_base import OrganisationScopedAdminMixin
from accounts.tenancy import get_request_organisation
from races import services
from races.models import (
    BillingUsageRecord,
    Checkpoint,
    Participant,
    Profile,
    Race,
    RaceVolunteer,
    Timing,
)
from races.resources import ParticipantResource


class CheckpointInline(admin.TabularInline):
    model = Checkpoint
    extra = 1
    ordering = ("sequence_order",)


@admin.register(Race)
class RaceAdmin(OrganisationScopedAdminMixin, admin.ModelAdmin):
    tenant_filter_path = "organisation"
    list_display = ("name", "event_date", "start_time", "status", "participant_count_cache")
    list_filter = ("status",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [CheckpointInline]
    readonly_fields = ("participant_count_cache",)


@admin.register(Checkpoint)
class CheckpointAdmin(OrganisationScopedAdminMixin, admin.ModelAdmin):
    tenant_filter_path = "race__organisation"
    list_display = ("name", "race", "sequence_order", "type")
    list_filter = ("type",)
    ordering = ("race", "sequence_order")


@admin.register(RaceVolunteer)
class RaceVolunteerAdmin(OrganisationScopedAdminMixin, admin.ModelAdmin):
    tenant_filter_path = "race__organisation"
    list_display = ("user", "race", "checkpoint", "invited_at", "accepted_at")
    list_filter = ("race",)
    search_fields = ("user__email",)
    autocomplete_fields = ["user"]
    actions = ["send_magic_link"]

    @admin.action(description="Send/resend magic link (shows the URL here)")
    def send_magic_link(self, request, queryset):
        # Creating a RaceVolunteer row here does NOT by itself issue a
        # magic link (that only happens via the API's invite endpoint) —
        # this action is how you actually get a copyable login URL for
        # someone added through this Admin page, and how you regenerate
        # one if an email never arrived (e.g. no SMTP configured, so
        # DJANGO_EMAIL_BACKEND is just logging it instead of delivering).
        for assignment in queryset.select_related("user", "race"):
            url = services.issue_volunteer_invite(assignment)
            self.message_user(
                request,
                f"{assignment.user.email} — {assignment.race.name}: {url}",
                level=messages.SUCCESS,
            )


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    """Not organisation-scoped by model design (§10) — an organiser is
    shown only profiles that have actually raced with their organisation
    at least once, via the Participant join, never another organiser's
    full roster."""

    list_display = ("full_name", "email", "itra_id", "qr_code_uuid")
    search_fields = ("full_name", "email", "itra_id")
    readonly_fields = ("qr_code_uuid",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        organisation = get_request_organisation(request.user)
        if organisation is None:
            return qs.none()
        return qs.filter(participations__race__organisation=organisation).distinct()

    def _member_or_superuser(self, request):
        if request.user.is_superuser:
            return True
        return get_request_organisation(request.user) is not None

    def has_module_permission(self, request):
        return self._member_or_superuser(request)

    def has_view_permission(self, request, obj=None):
        return self._member_or_superuser(request)

    def has_change_permission(self, request, obj=None):
        return self._member_or_superuser(request)

    def has_add_permission(self, request):
        # An organiser needs to be able to create a brand-new person's
        # Profile directly when adding a participant who doesn't already
        # exist anywhere on the platform (Participant's `profile` field
        # is a plain FK picker, not the nested create-or-reuse-by-email
        # the API does — see ParticipantAdmin.autocomplete_fields below).
        return self._member_or_superuser(request)

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(Participant)
class ParticipantAdmin(OrganisationScopedAdminMixin, ImportExportModelAdmin, admin.ModelAdmin):
    tenant_filter_path = "race__organisation"
    resource_classes = [ParticipantResource]
    list_display = ("bib_number", "profile", "race", "category", "status")
    list_filter = ("race", "status")
    search_fields = ("bib_number", "profile__full_name", "profile__email")
    autocomplete_fields = ["profile"]

    def get_import_resource_kwargs(self, request, *args, **kwargs):
        result = super().get_import_resource_kwargs(request, *args, **kwargs)
        result["organisation"] = get_request_organisation(request.user)
        return result


@admin.register(Timing)
class TimingAdmin(OrganisationScopedAdminMixin, admin.ModelAdmin):
    tenant_filter_path = "checkpoint__race__organisation"
    list_display = (
        "checkpoint",
        "participant",
        "unmatched_bib",
        "timestamp",
        "mode",
        "success",
        "is_duplicate",
    )
    list_filter = ("mode", "success", "is_duplicate", "checkpoint__race")
    search_fields = ("participant__bib_number", "unmatched_bib", "device_id")
    readonly_fields = ("client_event_id", "server_received_at", "created_at", "recorded_by_user")


@admin.register(BillingUsageRecord)
class BillingUsageRecordAdmin(OrganisationScopedAdminMixin, admin.ModelAdmin):
    """Read-only: usage/billing is computed by the system (§11), not
    hand-edited by an organiser. Viewable here since v0 has no dedicated
    billing UI (§3)."""

    tenant_filter_path = "organisation"
    list_display = (
        "race",
        "participant_count",
        "billable_participants",
        "unit_price",
        "amount_due",
        "status",
        "computed_at",
    )
    list_filter = ("status",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
