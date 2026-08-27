"""
Core business logic that isn't pure CRUD: duplicate-scan detection,
results compilation (§13), and usage/billing computation (§11).
"""

from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from races.models import BillingUsageRecord, Timing


def detect_duplicate(checkpoint, participant, timestamp, exclude_pk=None):
    """A second scan of the same participant at the same checkpoint within
    the configurable window (§9, requirement #12) is a duplicate. Returns
    True if an existing non-duplicate row already covers this window."""
    if participant is None:
        return False
    window = timezone.timedelta(seconds=settings.DUPLICATE_SCAN_WINDOW_SECONDS)
    qs = Timing.objects.filter(
        checkpoint=checkpoint,
        participant=participant,
        is_duplicate=False,
        timestamp__gte=timestamp - window,
        timestamp__lte=timestamp + window,
    )
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.exists()


@transaction.atomic
def compute_billing_usage_record(race):
    """Snapshot participant count / billable amount for a race into
    BillingUsageRecords (§11). Safe to call repeatedly — it always creates
    a fresh snapshot row rather than mutating history."""
    participant_count = race.recompute_participant_count_cache()
    threshold = settings.BILLING_FREE_PARTICIPANT_THRESHOLD
    billable = max(0, participant_count - threshold)
    unit_price = Decimal(settings.BILLING_UNIT_PRICE)
    amount_due = (Decimal(billable) * unit_price).quantize(Decimal("0.01"))

    return BillingUsageRecord.objects.create(
        race=race,
        organisation=race.organisation,
        participant_count=participant_count,
        billable_participants=billable,
        unit_price=unit_price,
        amount_due=amount_due,
        currency="USD",
        status=BillingUsageRecord.Status.PENDING,
    )


def compile_results(race):
    """Per participant: ordered checkpoint timestamps, computed splits,
    and total elapsed time from start (§6 requirement #13).

    Uses the first non-duplicate, successful Timing per (checkpoint,
    participant) — matching the duplicate-handling rule in §9.
    """
    checkpoints = list(race.checkpoints.order_by("sequence_order"))
    start_checkpoint = next((c for c in checkpoints if c.type == c.Type.START), None)

    participants = race.participants.select_related("profile").order_by("bib_number")

    timings = (
        Timing.objects.filter(
            checkpoint__race=race, is_duplicate=False, success=True, participant__isnull=False
        )
        .order_by("participant_id", "checkpoint_id", "timestamp")
    )

    # First non-duplicate successful timing per (participant, checkpoint).
    first_timing = {}
    for t in timings:
        key = (t.participant_id, t.checkpoint_id)
        if key not in first_timing:
            first_timing[key] = t

    results = []
    for participant in participants:
        splits = []
        previous_ts = None
        start_ts = first_timing.get((participant.id, start_checkpoint.id)).timestamp if (
            start_checkpoint and (participant.id, start_checkpoint.id) in first_timing
        ) else None

        for checkpoint in checkpoints:
            timing = first_timing.get((participant.id, checkpoint.id))
            ts = timing.timestamp if timing else None
            split_seconds = (ts - previous_ts).total_seconds() if (ts and previous_ts) else None
            elapsed_seconds = (ts - start_ts).total_seconds() if (ts and start_ts) else None
            splits.append(
                {
                    "checkpoint_id": checkpoint.id,
                    "checkpoint_name": checkpoint.name,
                    "sequence_order": checkpoint.sequence_order,
                    "timestamp": ts.isoformat() if ts else None,
                    "split_seconds": split_seconds,
                    "elapsed_seconds": elapsed_seconds,
                }
            )
            if ts:
                previous_ts = ts

        finish_checkpoint = next((c for c in checkpoints if c.type == c.Type.FINISH), None)
        finish_timing = first_timing.get((participant.id, finish_checkpoint.id)) if finish_checkpoint else None
        total_elapsed_seconds = (
            (finish_timing.timestamp - start_ts).total_seconds()
            if (finish_timing and start_ts)
            else None
        )

        results.append(
            {
                "participant_id": participant.id,
                "bib_number": participant.bib_number,
                "full_name": participant.profile.full_name,
                "category": participant.category,
                "status": participant.status,
                "splits": splits,
                "total_elapsed_seconds": total_elapsed_seconds,
            }
        )

    return results
