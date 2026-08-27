from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.auth import build_magic_link_url, issue_session_token
from accounts.models import MagicLink, OrganisationMember, User
from accounts.serializers import (
    MagicLinkConsumeSerializer,
    MagicLinkRequestSerializer,
    UserSummarySerializer,
)
from accounts.tasks import send_magic_link_email


class MagicLinkRequestView(APIView):
    """POST /api/auth/magic-link/request — organiser or volunteer requests
    a login link (§12). Also used to resend a volunteer's invite link."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = MagicLinkRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        purpose = serializer.validated_data["purpose"]
        race_id = serializer.validated_data.get("race_id")

        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            return Response(
                {"detail": "No account found for that email."},
                status=status.HTTP_404_NOT_FOUND,
            )

        race = None
        if purpose == MagicLink.Purpose.ORGANISER_LOGIN:
            if not OrganisationMember.objects.filter(user=user).exists():
                return Response(
                    {"detail": "This account is not an organisation member."},
                    status=status.HTTP_403_FORBIDDEN,
                )
        else:  # volunteer_login
            from races.models import RaceVolunteer

            if not race_id:
                return Response(
                    {"detail": "race_id is required for a volunteer login link."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            assignment = (
                RaceVolunteer.objects.select_related("race")
                .filter(user=user, race_id=race_id)
                .first()
            )
            if assignment is None:
                return Response(
                    {"detail": "This account is not assigned to that race."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            race = assignment.race

        from django.conf import settings

        link, raw_token = MagicLink.issue(
            user, purpose, race=race, ttl_minutes=settings.MAGIC_LINK_TTL_MINUTES
        )
        url = build_magic_link_url(raw_token)
        send_magic_link_email.delay(
            user.email, user.name, url, purpose, race.name if race else None
        )

        # Returned directly (not just emailed) so an organiser can copy the
        # same link to forward via WhatsApp/SMS (requirement #7).
        return Response({"detail": "Magic link sent.", "magic_link_url": url})


class MagicLinkConsumeView(APIView):
    """POST /api/auth/magic-link/consume — exchange a magic-link token for
    a session (§12)."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = MagicLinkConsumeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        raw_token = serializer.validated_data["token"]

        link = MagicLink.consume(raw_token)
        if link is None:
            return Response(
                {"detail": "This link is invalid, expired, or already used."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = link.user
        race = link.race
        checkpoint = None
        roster = None

        payload = {
            "purpose": link.purpose,
            "user": UserSummarySerializer(user).data,
            "race": None,
            "checkpoint": None,
            "roster": None,
        }

        if link.purpose == MagicLink.Purpose.VOLUNTEER_LOGIN and race is not None:
            from races.models import RaceVolunteer
            from races.serializers import (
                CheckpointSerializer,
                RaceSerializer,
                RosterParticipantSerializer,
            )

            assignment = (
                RaceVolunteer.objects.select_related("checkpoint")
                .filter(user=user, race=race)
                .first()
            )
            checkpoint = assignment.checkpoint if assignment else None

            payload["race"] = RaceSerializer(race).data
            payload["checkpoint"] = CheckpointSerializer(checkpoint).data if checkpoint else None
            # Cached on-device on login per §9: the race's roster (bib,
            # name, profile QR uuid) so a scan resolves with zero signal.
            roster_qs = race.participants.select_related("profile").all()
            payload["roster"] = RosterParticipantSerializer(roster_qs, many=True).data

        session_token = issue_session_token(user, race=race, checkpoint=checkpoint)
        payload["session_token"] = session_token
        return Response(payload)
