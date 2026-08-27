from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMessage


@shared_task
def send_participant_qr_email(profile_id, race_id):
    from races.models import Profile, Race
    from races.qr import generate_qr_png_bytes

    try:
        profile = Profile.objects.get(pk=profile_id)
        race = Race.objects.get(pk=race_id)
    except (Profile.DoesNotExist, Race.DoesNotExist):
        return

    qr_bytes = generate_qr_png_bytes(str(profile.qr_code_uuid))

    subject = f"Your QR code for {race.name}"
    body = (
        f"Hi {profile.full_name},\n\n"
        f"You're registered for {race.name} on {race.event_date}.\n"
        "Your personal QR code is attached — show it on your phone or a "
        "printed copy at each checkpoint. It's the same code for every "
        "race you enter, so keep it handy.\n"
    )
    email = EmailMessage(subject, body, settings.DEFAULT_FROM_EMAIL, [profile.email])
    email.attach(f"qr-{profile.qr_code_uuid}.png", qr_bytes, "image/png")
    email.send()
