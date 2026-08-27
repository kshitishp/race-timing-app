from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from races.models import Participant


@receiver(post_save, sender=Participant)
def on_participant_saved(sender, instance, created, **kwargs):
    instance.race.recompute_participant_count_cache()
    if created:
        from races.tasks import send_participant_qr_email

        # Requirement #5: QR email sent within 1 minute of a participant
        # being added. Celery task (async in prod, eager in dev/test).
        send_participant_qr_email.delay(instance.profile_id, instance.race_id)


@receiver(post_delete, sender=Participant)
def on_participant_deleted(sender, instance, **kwargs):
    # instance.race may already be gone from the DB on cascade delete of
    # the race itself, but the in-memory FK still resolves for our count.
    try:
        instance.race.recompute_participant_count_cache()
    except Exception:
        pass
