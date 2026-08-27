from rest_framework import serializers

from accounts.models import User
from races.models import BillingUsageRecord, Checkpoint, Participant, Profile, Race, RaceVolunteer, Timing


class RaceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Race
        fields = [
            "id",
            "name",
            "slug",
            "event_date",
            "start_time",
            "timezone",
            "status",
            "participant_count_cache",
            "checkpoint_sequence_mode",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "participant_count_cache", "created_at", "updated_at"]


class CheckpointSerializer(serializers.ModelSerializer):
    class Meta:
        model = Checkpoint
        fields = ["id", "race", "name", "sequence_order", "type", "gps_lat", "gps_lng"]
        read_only_fields = ["id"]
        extra_kwargs = {"race": {"required": False}}


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = [
            "id",
            "email",
            "full_name",
            "date_of_birth",
            "gender",
            "itra_id",
            "phone",
            "emergency_contact_name",
            "emergency_contact_phone",
            "qr_code_uuid",
        ]
        read_only_fields = ["id", "qr_code_uuid"]


class ParticipantSerializer(serializers.ModelSerializer):
    """Read/write serializer for a race entry. On create, looks up or
    creates the underlying Profile by email (dedup key, §6 requirement
    #4) and nests its fields for input convenience."""

    profile = ProfileSerializer()

    class Meta:
        model = Participant
        fields = ["id", "race", "profile", "bib_number", "category", "status", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]
        extra_kwargs = {"race": {"required": False}}

    def create(self, validated_data):
        profile_data = validated_data.pop("profile")
        email = profile_data.pop("email")
        profile, _ = self._get_or_create_profile(email, profile_data)
        return Participant.objects.create(profile=profile, **validated_data)

    @staticmethod
    def _get_or_create_profile(email, profile_data):
        profile = Profile.objects.filter(email__iexact=email).first()
        if profile is None:
            profile = Profile.objects.create(email=email, **profile_data)
            return profile, True
        # Pre-fill/refresh the shareable core identity fields (§10) without
        # clobbering values the caller didn't send.
        changed = False
        for field, value in profile_data.items():
            if value not in (None, "") and getattr(profile, field) != value:
                setattr(profile, field, value)
                changed = True
        if changed:
            profile.save()
        return profile, False


class RosterParticipantSerializer(serializers.ModelSerializer):
    """Cached on-device at volunteer login (§9): bib, name, profile QR
    UUID — enough to resolve a scan/manual entry with zero signal."""

    full_name = serializers.CharField(source="profile.full_name")
    profile_qr_uuid = serializers.UUIDField(source="profile.qr_code_uuid")

    class Meta:
        model = Participant
        fields = ["id", "bib_number", "full_name", "profile_qr_uuid", "category", "status"]


class UserInviteSerializer(serializers.Serializer):
    """Used to invite (or reuse) a volunteer by email on RaceVolunteer
    creation."""

    email = serializers.EmailField()
    name = serializers.CharField(required=False, allow_blank=True, default="")
    phone = serializers.CharField(required=False, allow_blank=True, default="")


class RaceVolunteerSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField(read_only=True)
    checkpoint_id = serializers.PrimaryKeyRelatedField(
        source="checkpoint", queryset=Checkpoint.objects.all()
    )

    class Meta:
        model = RaceVolunteer
        fields = ["id", "race", "checkpoint_id", "user", "invited_at", "accepted_at"]
        read_only_fields = ["id", "race", "invited_at", "accepted_at"]

    def get_user(self, obj):
        return {"id": obj.user_id, "email": obj.user.email, "name": obj.user.name}


class TimingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Timing
        fields = [
            "id",
            "checkpoint",
            "participant",
            "recorded_by_user",
            "device_id",
            "client_event_id",
            "timestamp",
            "server_received_at",
            "mode",
            "success",
            "is_duplicate",
            "unmatched_bib",
            "notes",
            "created_at",
        ]
        read_only_fields = fields


class BulkSyncItemSerializer(serializers.Serializer):
    client_event_id = serializers.UUIDField()
    bib_number = serializers.CharField()
    timestamp = serializers.DateTimeField()
    mode = serializers.ChoiceField(choices=Timing.Mode.choices)
    success = serializers.BooleanField(default=True)
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class TimingCorrectionSerializer(serializers.ModelSerializer):
    """Organiser-only mutation of an existing Timing row (requirement:
    "manually add or correct a timing record")."""

    class Meta:
        model = Timing
        fields = ["timestamp", "participant", "is_duplicate", "success", "notes"]


class BulkSyncRequestSerializer(serializers.Serializer):
    device_id = serializers.CharField(required=False, allow_blank=True, default="")
    items = BulkSyncItemSerializer(many=True)


class BillingUsageRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = BillingUsageRecord
        fields = [
            "id",
            "race",
            "organisation",
            "participant_count",
            "billable_participants",
            "unit_price",
            "amount_due",
            "currency",
            "status",
            "computed_at",
            "invoice_reference",
        ]
        read_only_fields = fields
