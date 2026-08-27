import uuid
from datetime import date, time

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.auth import issue_session_token
from accounts.models import MagicLink, Organisation, OrganisationMember, User
from races import services
from races.models import BillingUsageRecord, Checkpoint, Participant, Profile, Race, Timing


def make_organisation(name="Trail Runners Co"):
    return Organisation.objects.create(name=name, slug=name.lower().replace(" ", "-"), billing_email="b@example.com")


def make_race(organisation, name="Mountain 50K"):
    return Race.objects.create(
        organisation=organisation,
        name=name,
        slug=name.lower().replace(" ", "-"),
        event_date=date(2026, 9, 1),
        start_time=time(6, 0),
    )


def make_checkpoints(race):
    start = Checkpoint.objects.create(race=race, name="Start", sequence_order=1, type=Checkpoint.Type.START)
    cp1 = Checkpoint.objects.create(race=race, name="CP1", sequence_order=2, type=Checkpoint.Type.CHECKPOINT)
    finish = Checkpoint.objects.create(race=race, name="Finish", sequence_order=3, type=Checkpoint.Type.FINISH)
    return start, cp1, finish


def make_participant(race, email="runner@example.com", bib="101", name="Jane Doe"):
    profile = Profile.objects.create(email=email, full_name=name)
    return Participant.objects.create(race=race, profile=profile, bib_number=bib)


class TenancyIsolationTests(TestCase):
    """§10: cross-tenant queries must return nothing."""

    def test_race_queryset_scoped_to_organisation(self):
        org_a = make_organisation("Org A")
        org_b = make_organisation("Org B")
        race_a = make_race(org_a, "Race A")
        make_race(org_b, "Race B")

        visible_to_a = Race.objects.for_organisation(org_a)
        self.assertEqual(list(visible_to_a), [race_a])

    def test_api_race_list_is_organisation_scoped(self):
        org_a = make_organisation("Org A")
        org_b = make_organisation("Org B")
        race_a = make_race(org_a, "Race A")
        make_race(org_b, "Race B")

        user_a = User.objects.create_user(email="organiser-a@example.com")
        OrganisationMember.objects.create(organisation=org_a, user=user_a, role=OrganisationMember.Role.OWNER)

        token = issue_session_token(user_a)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = client.get(reverse("race-list"))

        self.assertEqual(response.status_code, 200)
        ids = [r["id"] for r in response.json()]
        self.assertEqual(ids, [race_a.id])


class MagicLinkAuthTests(TestCase):
    def test_volunteer_consume_returns_session_token_and_cached_roster(self):
        org = make_organisation()
        race = make_race(org)
        start, cp1, finish = make_checkpoints(race)
        make_participant(race, bib="142", name="Jane Doe")

        from races.models import RaceVolunteer

        volunteer = User.objects.create_user(email="vol@example.com", name="Val Unteer")
        RaceVolunteer.objects.create(race=race, checkpoint=cp1, user=volunteer)

        link, raw_token = MagicLink.issue(volunteer, MagicLink.Purpose.VOLUNTEER_LOGIN, race=race, ttl_minutes=60)

        client = APIClient()
        response = client.post(reverse("magic-link-consume"), {"token": raw_token})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("session_token", body)
        self.assertEqual(body["checkpoint"]["id"], cp1.id)
        self.assertEqual(len(body["roster"]), 1)
        self.assertEqual(body["roster"][0]["bib_number"], "142")

    def test_expired_or_used_link_is_rejected(self):
        org = make_organisation()
        user = User.objects.create_user(email="organiser@example.com")
        OrganisationMember.objects.create(organisation=org, user=user)
        link, raw_token = MagicLink.issue(user, MagicLink.Purpose.ORGANISER_LOGIN, ttl_minutes=60)

        client = APIClient()
        first = client.post(reverse("magic-link-consume"), {"token": raw_token})
        self.assertEqual(first.status_code, 200)

        second = client.post(reverse("magic-link-consume"), {"token": raw_token})
        self.assertEqual(second.status_code, 400)


class BulkSyncIdempotencyTests(TestCase):
    def _volunteer_client(self):
        org = make_organisation()
        race = make_race(org)
        start, cp1, finish = make_checkpoints(race)
        participant = make_participant(race, bib="142")

        from races.models import RaceVolunteer

        volunteer = User.objects.create_user(email="vol@example.com")
        RaceVolunteer.objects.create(race=race, checkpoint=cp1, user=volunteer)

        token = issue_session_token(volunteer, race=race, checkpoint=cp1)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        return client, race, cp1, participant

    def test_retried_batch_never_creates_duplicate_rows(self):
        client, race, cp1, participant = self._volunteer_client()
        client_event_id = str(uuid.uuid4())
        payload = {
            "device_id": "device-1",
            "items": [
                {
                    "client_event_id": client_event_id,
                    "bib_number": "142",
                    "timestamp": timezone.now().isoformat(),
                    "mode": "qr",
                    "success": True,
                }
            ],
        }

        first = client.post(reverse("timing-bulk-sync"), payload, format="json")
        second = client.post(reverse("timing-bulk-sync"), payload, format="json")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["results"][0]["status"], "created")
        self.assertEqual(second.json()["results"][0]["status"], "already_synced")
        self.assertEqual(Timing.objects.filter(client_event_id=client_event_id).count(), 1)

    def test_unmatched_bib_is_logged_not_dropped(self):
        client, race, cp1, participant = self._volunteer_client()
        payload = {
            "device_id": "device-1",
            "items": [
                {
                    "client_event_id": str(uuid.uuid4()),
                    "bib_number": "999-does-not-exist",
                    "timestamp": timezone.now().isoformat(),
                    "mode": "manual",
                }
            ],
        }
        response = client.post(reverse("timing-bulk-sync"), payload, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["results"][0]["matched"])
        timing = Timing.objects.get(unmatched_bib="999-does-not-exist")
        self.assertFalse(timing.success)
        self.assertIsNone(timing.participant)


class DuplicateScanDetectionTests(TestCase):
    def test_second_scan_within_window_is_flagged_not_dropped(self):
        org = make_organisation()
        race = make_race(org)
        start, cp1, finish = make_checkpoints(race)
        participant = make_participant(race, bib="142")

        now = timezone.now()
        first = Timing.objects.create(
            checkpoint=cp1,
            participant=participant,
            client_event_id=uuid.uuid4(),
            timestamp=now,
            mode=Timing.Mode.QR,
        )
        is_dup = services.detect_duplicate(cp1, participant, now + timezone.timedelta(seconds=30))
        self.assertTrue(is_dup)

        second = Timing.objects.create(
            checkpoint=cp1,
            participant=participant,
            client_event_id=uuid.uuid4(),
            timestamp=now + timezone.timedelta(seconds=30),
            mode=Timing.Mode.QR,
            is_duplicate=is_dup,
        )
        self.assertEqual(Timing.objects.filter(checkpoint=cp1, participant=participant).count(), 2)
        self.assertFalse(Timing.objects.get(pk=first.pk).is_duplicate)
        self.assertTrue(Timing.objects.get(pk=second.pk).is_duplicate)


class ResultsCompilationTests(TestCase):
    def test_splits_and_total_elapsed_are_computed(self):
        org = make_organisation()
        race = make_race(org)
        start, cp1, finish = make_checkpoints(race)
        participant = make_participant(race, bib="142")

        base = timezone.now()
        for checkpoint, offset in [(start, 0), (cp1, 1800), (finish, 5400)]:
            Timing.objects.create(
                checkpoint=checkpoint,
                participant=participant,
                client_event_id=uuid.uuid4(),
                timestamp=base + timezone.timedelta(seconds=offset),
                mode=Timing.Mode.QR,
            )

        results = services.compile_results(race)
        self.assertEqual(len(results), 1)
        row = results[0]
        self.assertEqual(row["total_elapsed_seconds"], 5400)
        self.assertEqual(row["splits"][1]["split_seconds"], 1800)


class BillingUsageTests(TestCase):
    def test_billable_participants_floor_at_zero_and_charge_above_threshold(self):
        org = make_organisation()
        race = make_race(org)
        for i in range(3):
            make_participant(race, email=f"runner{i}@example.com", bib=str(100 + i))

        record = services.compute_billing_usage_record(race)
        self.assertEqual(record.participant_count, 3)
        self.assertEqual(record.billable_participants, 0)
        self.assertEqual(str(record.amount_due), "0.00")

        for i in range(3, 55):
            make_participant(race, email=f"runner{i}@example.com", bib=str(100 + i))

        record = services.compute_billing_usage_record(race)
        self.assertEqual(record.participant_count, 55)
        self.assertEqual(record.billable_participants, 5)
        self.assertEqual(str(record.amount_due), "5.00")
