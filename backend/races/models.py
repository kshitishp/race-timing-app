import uuid

from django.conf import settings
from django.db import models

from accounts.tenancy import OrganisationScopedManager


class Race(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        ARCHIVED = "archived", "Archived"

    class CheckpointSequenceMode(models.TextChoices):
        STRICT = "strict", "Strict order"
        ANY = "any", "Any order between start and finish"

    TENANT_FILTER_PATH = "organisation"

    organisation = models.ForeignKey(
        "accounts.Organisation", on_delete=models.CASCADE, related_name="races"
    )
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)
    event_date = models.DateField()
    start_time = models.TimeField()
    timezone = models.CharField(max_length=64, default="UTC")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    participant_count_cache = models.PositiveIntegerField(default=0)
    checkpoint_sequence_mode = models.CharField(
        max_length=8, choices=CheckpointSequenceMode.choices, default=CheckpointSequenceMode.STRICT
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = OrganisationScopedManager()

    class Meta:
        unique_together = ("organisation", "slug")
        ordering = ["-event_date"]

    def __str__(self):
        return f"{self.name} ({self.event_date})"

    def recompute_participant_count_cache(self):
        count = self.participants.count()
        if count != self.participant_count_cache:
            self.participant_count_cache = count
            self.save(update_fields=["participant_count_cache"])
        return count


class Checkpoint(models.Model):
    class Type(models.TextChoices):
        START = "start", "Start"
        CHECKPOINT = "checkpoint", "Checkpoint"
        FINISH = "finish", "Finish"

    TENANT_FILTER_PATH = "race__organisation"

    race = models.ForeignKey(Race, on_delete=models.CASCADE, related_name="checkpoints")
    name = models.CharField(max_length=255)
    sequence_order = models.PositiveIntegerField()
    type = models.CharField(max_length=16, choices=Type.choices, default=Type.CHECKPOINT)
    gps_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    gps_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    # Reserved for the future participant-app self-scan mode (§6 P2) — unused in v1.
    self_scan_code = models.CharField(max_length=64, null=True, blank=True)

    objects = OrganisationScopedManager()

    class Meta:
        unique_together = ("race", "sequence_order")
        ordering = ["race_id", "sequence_order"]

    def __str__(self):
        return f"{self.race.name} — {self.name}"


class RaceVolunteer(models.Model):
    TENANT_FILTER_PATH = "race__organisation"

    race = models.ForeignKey(Race, on_delete=models.CASCADE, related_name="volunteer_assignments")
    checkpoint = models.ForeignKey(
        Checkpoint, on_delete=models.CASCADE, related_name="volunteer_assignments"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="race_volunteer_assignments",
    )
    invited_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)

    objects = OrganisationScopedManager()

    class Meta:
        unique_together = ("race", "checkpoint", "user")

    def __str__(self):
        return f"{self.user.email} @ {self.checkpoint} ({self.race.name})"


class Profile(models.Model):
    """Source of truth for a person's identity — deliberately NOT
    organisation-scoped; reusable across races and organisations (§8, §10).
    No TENANT_FILTER_PATH: this model is intentionally excluded from tenant
    filtering."""

    email = models.EmailField(unique=True)

    # Shareable core identity (pre-filled across organisations by default
    # in v0 — no consent gate yet, see §6 P1).
    full_name = models.CharField(max_length=255)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=32, blank=True)
    itra_id = models.CharField(max_length=64, blank=True)

    # Organisation-private fields — never surfaced to an organisation the
    # profile hasn't itself registered with.
    phone = models.CharField(max_length=32, blank=True)
    emergency_contact_name = models.CharField(max_length=255, blank=True)
    emergency_contact_phone = models.CharField(max_length=32, blank=True)

    # Generated once, reused on every race the person enters — never
    # regenerated per race.
    qr_code_uuid = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)

    # Reserved/unused in v0 — for the future P1 consent gate (§6, §8).
    cross_org_sharing_consent_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.full_name} <{self.email}>"


class Participant(models.Model):
    """A Profile's entry into one specific Race."""

    class Status(models.TextChoices):
        REGISTERED = "registered", "Registered"
        CHECKED_IN = "checked_in", "Checked in"
        DNF = "dnf", "DNF"
        DNS = "dns", "DNS"
        FINISHED = "finished", "Finished"

    TENANT_FILTER_PATH = "race__organisation"

    race = models.ForeignKey(Race, on_delete=models.CASCADE, related_name="participants")
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="participations")
    bib_number = models.CharField(max_length=32)
    category = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.REGISTERED)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = OrganisationScopedManager()

    class Meta:
        unique_together = (("race", "profile"), ("race", "bib_number"))
        ordering = ["bib_number"]

    def __str__(self):
        return f"#{self.bib_number} {self.profile.full_name} — {self.race.name}"


class TimingQuerySet(models.QuerySet):
    def for_organisation(self, organisation):
        return self.filter(checkpoint__race__organisation=organisation)


class Timing(models.Model):
    class Mode(models.TextChoices):
        QR = "qr", "QR scan"
        MANUAL = "manual", "Manual entry"

    TENANT_FILTER_PATH = "checkpoint__race__organisation"

    checkpoint = models.ForeignKey(Checkpoint, on_delete=models.CASCADE, related_name="timings")
    participant = models.ForeignKey(
        Participant, on_delete=models.CASCADE, related_name="timings", null=True, blank=True
    )
    recorded_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_timings",
    )
    device_id = models.CharField(max_length=128, blank=True)
    # Idempotency key generated on-device at capture time.
    client_event_id = models.UUIDField(unique=True)
    # Device-captured local time, converted to UTC for storage, trusted
    # as-is with no offset correction (§9).
    timestamp = models.DateTimeField()
    server_received_at = models.DateTimeField(null=True, blank=True)
    mode = models.CharField(max_length=8, choices=Mode.choices)
    success = models.BooleanField(default=True)
    is_duplicate = models.BooleanField(default=False)
    # Present when a scanned/entered bib didn't match the cached roster
    # (§9) — the record is still kept, never silently dropped.
    unmatched_bib = models.CharField(max_length=32, blank=True)
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TimingQuerySet.as_manager()

    class Meta:
        indexes = [models.Index(fields=["checkpoint", "participant"])]
        ordering = ["timestamp"]

    def __str__(self):
        return f"{self.checkpoint} — {self.participant or self.unmatched_bib} @ {self.timestamp}"


class BillingUsageRecord(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        INVOICED = "invoiced", "Invoiced"
        PAID = "paid", "Paid"
        WAIVED = "waived", "Waived"

    TENANT_FILTER_PATH = "organisation"

    race = models.ForeignKey(Race, on_delete=models.CASCADE, related_name="billing_usage_records")
    # Denormalized for reporting.
    organisation = models.ForeignKey(
        "accounts.Organisation", on_delete=models.CASCADE, related_name="billing_usage_records"
    )
    participant_count = models.PositiveIntegerField()
    billable_participants = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=8, decimal_places=2, default="1.00")
    amount_due = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=8, default="USD")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    computed_at = models.DateTimeField(auto_now_add=True)
    invoice_reference = models.CharField(max_length=128, blank=True)

    objects = OrganisationScopedManager()

    def __str__(self):
        return f"{self.race.name}: {self.billable_participants} billable @ {self.unit_price}"
