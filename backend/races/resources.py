"""django-import-export Resource for Participant CSV import via Django
Admin (§6 confirmed decision: "django-import-export ... for CSV import
essentially for free"). The same capability is also exposed on the API
(races/views.py ParticipantListCreateView._import_csv) for the PWA/future
organiser tooling — this Admin path is the zero-build option for v0.
"""

from import_export import fields, resources
from import_export.widgets import ForeignKeyWidget

from races.models import Participant, Profile, Race


class ParticipantResource(resources.ModelResource):
    race = fields.Field(
        column_name="race_id", attribute="race", widget=ForeignKeyWidget(Race, "id")
    )
    profile = fields.Field(
        column_name="profile_id", attribute="profile", widget=ForeignKeyWidget(Profile, "id")
    )

    class Meta:
        model = Participant
        fields = ("id", "race", "profile", "bib_number", "category", "status")
        import_id_fields = ("race", "bib_number")

    def __init__(self, organisation=None, **kwargs):
        super().__init__(**kwargs)
        self.organisation = organisation

    def before_import_row(self, row, row_number=None, **kwargs):
        email = (row.get("profile_email") or "").strip()
        if not email:
            raise ValueError(f"Row {row_number}: profile_email is required.")

        profile, _ = Profile.objects.get_or_create(
            email__iexact=email, defaults={"email": email}
        )
        core_fields = {
            "full_name": row.get("profile_full_name"),
            "date_of_birth": row.get("profile_date_of_birth") or None,
            "gender": row.get("profile_gender"),
            "itra_id": row.get("profile_itra_id"),
            "phone": row.get("profile_phone"),
            "emergency_contact_name": row.get("profile_emergency_contact_name"),
            "emergency_contact_phone": row.get("profile_emergency_contact_phone"),
        }
        changed = False
        for field_name, value in core_fields.items():
            if value:
                setattr(profile, field_name, value)
                changed = True
        if changed:
            profile.save()
        row["profile_id"] = profile.id

        race_id = row.get("race_id")
        if self.organisation is not None and race_id:
            if not Race.objects.filter(pk=race_id, organisation=self.organisation).exists():
                raise ValueError(
                    f"Row {row_number}: race_id {race_id} is not one of your organisation's races."
                )
