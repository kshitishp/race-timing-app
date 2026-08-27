import csv
import io
import uuid

from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from accounts.permissions import IsOrganisationMember, IsVolunteerSession
from accounts.tenancy import get_request_organisation
from races import services
from races.export import get_formatter
from races.models import Checkpoint, Participant, Race, RaceVolunteer, Timing
from races.serializers import (
    BillingUsageRecordSerializer,
    BulkSyncRequestSerializer,
    CheckpointSerializer,
    ParticipantSerializer,
    RaceSerializer,
    RaceVolunteerSerializer,
    TimingCorrectionSerializer,
    TimingSerializer,
    UserInviteSerializer,
)


class OrganisationScopedAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsOrganisationMember]

    def get_organisation(self, request):
        return get_request_organisation(request.user)


# ---------------------------------------------------------------------
# Races
# ---------------------------------------------------------------------


class RaceListCreateView(OrganisationScopedAPIView):
    def get(self, request):
        organisation = self.get_organisation(request)
        races = Race.objects.for_organisation(organisation)
        return Response(RaceSerializer(races, many=True).data)

    def post(self, request):
        organisation = self.get_organisation(request)
        serializer = RaceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        race = serializer.save(organisation=organisation)
        return Response(RaceSerializer(race).data, status=status.HTTP_201_CREATED)


class RaceDetailView(OrganisationScopedAPIView):
    def get_object(self, request, pk):
        organisation = self.get_organisation(request)
        return get_object_or_404(Race.objects.for_organisation(organisation), pk=pk)

    def get(self, request, pk):
        return Response(RaceSerializer(self.get_object(request, pk)).data)

    def patch(self, request, pk):
        race = self.get_object(request, pk)
        serializer = RaceSerializer(race, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


# ---------------------------------------------------------------------
# Checkpoints
# ---------------------------------------------------------------------


class CheckpointListCreateView(OrganisationScopedAPIView):
    def get(self, request, race_id):
        organisation = self.get_organisation(request)
        race = get_object_or_404(Race.objects.for_organisation(organisation), pk=race_id)
        checkpoints = race.checkpoints.all()
        return Response(CheckpointSerializer(checkpoints, many=True).data)

    def post(self, request, race_id):
        organisation = self.get_organisation(request)
        race = get_object_or_404(Race.objects.for_organisation(organisation), pk=race_id)
        # race is injected into the payload (not just passed to save())
        # because Checkpoint's (race, sequence_order) unique_together
        # constraint makes DRF's auto-generated UniqueTogetherValidator
        # require it to be present in validated input.
        data = {**request.data, "race": race.id}
        serializer = CheckpointSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        checkpoint = serializer.save()
        return Response(CheckpointSerializer(checkpoint).data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------
# Participants (manual add + CSV import)
# ---------------------------------------------------------------------


class ParticipantListCreateView(OrganisationScopedAPIView):
    def get(self, request, race_id):
        organisation = self.get_organisation(request)
        race = get_object_or_404(Race.objects.for_organisation(organisation), pk=race_id)
        participants = race.participants.select_related("profile").all()
        return Response(ParticipantSerializer(participants, many=True).data)

    def post(self, request, race_id):
        organisation = self.get_organisation(request)
        race = get_object_or_404(Race.objects.for_organisation(organisation), pk=race_id)

        if request.content_type and "multipart" in request.content_type and "csv_file" in request.FILES:
            return self._import_csv(race, request.FILES["csv_file"])

        # race is injected into the payload (see CheckpointListCreateView
        # for why) because Participant's unique_together constraints need
        # it present for DRF's auto-generated validator.
        data = {**request.data, "race": race.id}
        serializer = ParticipantSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        try:
            participant = serializer.save()
        except IntegrityError:
            return Response(
                {"detail": "A participant with that bib number (or profile) already exists in this race."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(ParticipantSerializer(participant).data, status=status.HTTP_201_CREATED)

    def _import_csv(self, race, csv_file):
        """Bulk CSV import: bib_number,email,full_name,category,phone,...
        Row-level validation with an error report (P1, kept simple for
        v0's manual-import path)."""
        decoded = io.TextIOWrapper(csv_file.file, encoding="utf-8")
        reader = csv.DictReader(decoded)
        created, errors = [], []
        for line_no, row in enumerate(reader, start=2):
            row_data = {
                "race": race.id,
                "bib_number": (row.get("bib_number") or "").strip(),
                "category": (row.get("category") or "").strip(),
                "profile": {
                    "email": (row.get("email") or "").strip(),
                    "full_name": (row.get("full_name") or "").strip(),
                    "date_of_birth": (row.get("date_of_birth") or None) or None,
                    "gender": (row.get("gender") or "").strip(),
                    "itra_id": (row.get("itra_id") or "").strip(),
                    "phone": (row.get("phone") or "").strip(),
                    "emergency_contact_name": (row.get("emergency_contact_name") or "").strip(),
                    "emergency_contact_phone": (row.get("emergency_contact_phone") or "").strip(),
                },
            }
            serializer = ParticipantSerializer(data=row_data)
            if not serializer.is_valid():
                errors.append({"row": line_no, "errors": serializer.errors})
                continue
            try:
                with transaction.atomic():
                    participant = serializer.save()
            except IntegrityError:
                errors.append({"row": line_no, "errors": "Duplicate bib number or profile for this race."})
                continue
            created.append(ParticipantSerializer(participant).data)

        return Response({"created": created, "errors": errors}, status=status.HTTP_207_MULTI_STATUS)


# ---------------------------------------------------------------------
# Volunteers
# ---------------------------------------------------------------------


class RaceVolunteerListCreateView(OrganisationScopedAPIView):
    def get(self, request, race_id):
        organisation = self.get_organisation(request)
        race = get_object_or_404(Race.objects.for_organisation(organisation), pk=race_id)
        assignments = race.volunteer_assignments.select_related("user", "checkpoint").all()
        return Response(RaceVolunteerSerializer(assignments, many=True).data)

    def post(self, request, race_id):
        """Invite (or reuse) a volunteer by email, assign to a checkpoint,
        and issue a magic link — returned in the response so the organiser
        can copy/share it directly (requirement #7), and emailed async."""
        organisation = self.get_organisation(request)
        race = get_object_or_404(Race.objects.for_organisation(organisation), pk=race_id)

        invite_serializer = UserInviteSerializer(data=request.data)
        invite_serializer.is_valid(raise_exception=True)
        email = invite_serializer.validated_data["email"]
        name = invite_serializer.validated_data["name"]
        phone = invite_serializer.validated_data["phone"]

        checkpoint_id = request.data.get("checkpoint_id")
        checkpoint = get_object_or_404(Checkpoint, pk=checkpoint_id, race=race)

        user, _ = User.objects.get_or_create(
            email__iexact=email, defaults={"email": email, "name": name, "phone": phone}
        )

        assignment, created = RaceVolunteer.objects.get_or_create(
            race=race, checkpoint=checkpoint, user=user
        )

        url = services.issue_volunteer_invite(assignment)

        payload = RaceVolunteerSerializer(assignment).data
        payload["magic_link_url"] = url
        return Response(payload, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


# ---------------------------------------------------------------------
# Timings: bulk sync (volunteer, offline-first) + organiser corrections
# ---------------------------------------------------------------------


class BulkSyncView(APIView):
    """POST /api/timings/bulk-sync — idempotent batch upload of queued
    scans, keyed on client_event_id (§9, §12, requirement #9 & #10)."""

    permission_classes = [permissions.IsAuthenticated, IsVolunteerSession]

    def post(self, request):
        auth = request.auth or {}
        race_id = auth.get("race_id")
        checkpoint_id = auth.get("checkpoint_id")
        race = get_object_or_404(Race, pk=race_id)
        checkpoint = get_object_or_404(Checkpoint, pk=checkpoint_id, race=race)

        serializer = BulkSyncRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device_id = serializer.validated_data["device_id"]
        items = serializer.validated_data["items"]

        results = []
        for item in items:
            results.append(
                self._sync_one(request.user, checkpoint, device_id, item)
            )
        return Response({"results": results})

    def _sync_one(self, user, checkpoint, device_id, item):
        client_event_id = item["client_event_id"]

        existing = Timing.objects.filter(client_event_id=client_event_id).first()
        if existing is not None:
            # Idempotent replay: never create a second row for a retried
            # or partially-acknowledged batch (requirement #10).
            return {
                "client_event_id": str(client_event_id),
                "status": "already_synced",
                "timing_id": existing.id,
                "matched": existing.participant_id is not None,
            }

        bib_number = item["bib_number"]
        participant = (
            Participant.objects.filter(race=checkpoint.race, bib_number=bib_number)
            .select_related("profile")
            .first()
        )

        is_duplicate = (
            services.detect_duplicate(checkpoint, participant, item["timestamp"])
            if participant
            else False
        )

        try:
            timing = Timing.objects.create(
                checkpoint=checkpoint,
                participant=participant,
                recorded_by_user=user,
                device_id=device_id,
                client_event_id=client_event_id,
                timestamp=item["timestamp"],
                server_received_at=timezone.now(),
                mode=item["mode"],
                success=item["success"] if participant else False,
                is_duplicate=is_duplicate,
                unmatched_bib="" if participant else bib_number,
                notes=item.get("notes", ""),
            )
        except IntegrityError:
            # Lost the race to another concurrent request with the same
            # client_event_id — that row is authoritative either way.
            existing = Timing.objects.get(client_event_id=client_event_id)
            return {
                "client_event_id": str(client_event_id),
                "status": "already_synced",
                "timing_id": existing.id,
                "matched": existing.participant_id is not None,
            }

        return {
            "client_event_id": str(client_event_id),
            "status": "created",
            "timing_id": timing.id,
            "matched": participant is not None,
            "is_duplicate": is_duplicate,
        }


class TimingListView(OrganisationScopedAPIView):
    """GET /api/races/:id/timings — recent scan activity across
    checkpoints, so an organiser can spot a checkpoint gone quiet."""

    def get(self, request, race_id):
        organisation = self.get_organisation(request)
        race = get_object_or_404(Race.objects.for_organisation(organisation), pk=race_id)
        timings = (
            Timing.objects.filter(checkpoint__race=race)
            .select_related("checkpoint", "participant")
            .order_by("-server_received_at", "-created_at")[:500]
        )
        return Response(TimingSerializer(timings, many=True).data)


class TimingDetailView(OrganisationScopedAPIView):
    """PATCH /api/timings/:id — organiser manually adds/corrects a timing
    record (requirement #11/#12 acceptance: audit trail preserved via
    notes; the row itself is mutable by the organiser only)."""

    def get_object(self, request, pk):
        organisation = self.get_organisation(request)
        return get_object_or_404(Timing.objects.for_organisation(organisation), pk=pk)

    def patch(self, request, pk):
        timing = self.get_object(request, pk)
        serializer = TimingCorrectionSerializer(timing, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(TimingSerializer(timing).data)


class TimingManualCreateView(OrganisationScopedAPIView):
    """POST /api/races/:id/timings — organiser manually adds a missed
    timing record."""

    def post(self, request, race_id):
        organisation = self.get_organisation(request)
        race = get_object_or_404(Race.objects.for_organisation(organisation), pk=race_id)
        checkpoint = get_object_or_404(Checkpoint, pk=request.data.get("checkpoint_id"), race=race)
        participant = get_object_or_404(
            Participant, pk=request.data.get("participant_id"), race=race
        )
        timestamp = request.data.get("timestamp") or timezone.now()

        timing = Timing.objects.create(
            checkpoint=checkpoint,
            participant=participant,
            recorded_by_user=request.user,
            client_event_id=uuid.uuid4(),
            timestamp=timestamp,
            server_received_at=timezone.now(),
            mode=Timing.Mode.MANUAL,
            success=True,
            is_duplicate=services.detect_duplicate(checkpoint, participant, timestamp),
            notes=request.data.get("notes", "Manually added by organiser"),
        )
        return Response(TimingSerializer(timing).data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------
# Results + export
# ---------------------------------------------------------------------


class ResultsView(OrganisationScopedAPIView):
    def get(self, request, race_id):
        organisation = self.get_organisation(request)
        race = get_object_or_404(Race.objects.for_organisation(organisation), pk=race_id)
        return Response({"race": RaceSerializer(race).data, "results": services.compile_results(race)})


class ResultsExportView(OrganisationScopedAPIView):
    def get(self, request, race_id):
        organisation = self.get_organisation(request)
        race = get_object_or_404(Race.objects.for_organisation(organisation), pk=race_id)
        format_name = request.query_params.get("format", "csv")
        formatter = get_formatter(format_name)
        if formatter is None:
            return Response(
                {"detail": f"Unsupported export format '{format_name}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        results = services.compile_results(race)
        body = formatter.render(race, results)
        response = HttpResponse(body, content_type=formatter.content_type)
        response["Content-Disposition"] = (
            f'attachment; filename="{race.slug}-results.{formatter.file_extension}"'
        )
        return response


# ---------------------------------------------------------------------
# Billing (read-only, backend-only per §3/§11 — no dedicated UI in v0)
# ---------------------------------------------------------------------


class BillingUsageListView(OrganisationScopedAPIView):
    def get(self, request, race_id):
        organisation = self.get_organisation(request)
        race = get_object_or_404(Race.objects.for_organisation(organisation), pk=race_id)
        records = race.billing_usage_records.all().order_by("-computed_at")
        return Response(BillingUsageRecordSerializer(records, many=True).data)

    def post(self, request, race_id):
        organisation = self.get_organisation(request)
        race = get_object_or_404(Race.objects.for_organisation(organisation), pk=race_id)
        record = services.compute_billing_usage_record(race)
        return Response(BillingUsageRecordSerializer(record).data, status=status.HTTP_201_CREATED)
