from rest_framework.permissions import BasePermission

from accounts.tenancy import get_request_organisation


class IsOrganisationMember(BasePermission):
    """Request is authenticated as an organiser belonging to at least one
    organisation. The resolved organisation is attached to the view via
    `get_request_organisation` inside the view itself."""

    message = "You are not a member of any organisation."

    def has_permission(self, request, view):
        return get_request_organisation(request.user) is not None


class IsVolunteerSession(BasePermission):
    """Request carries a volunteer-scoped session token (race_id present
    in the JWT payload set at magic-link consume time)."""

    message = "This session is not scoped to a race/checkpoint."

    def has_permission(self, request, view):
        auth = request.auth or {}
        return bool(auth.get("race_id"))
