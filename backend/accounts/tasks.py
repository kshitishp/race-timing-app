from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail


@shared_task
def send_magic_link_email(user_email, user_name, magic_link_url, purpose, race_name=None):
    if purpose == "volunteer_login":
        subject = f"Your volunteer login link{f' — {race_name}' if race_name else ''}"
        body = (
            f"Hi {user_name or ''},\n\n"
            f"Here is your login link for checkpoint scanning"
            f"{f' at {race_name}' if race_name else ''}. It works without a password:\n\n"
            f"{magic_link_url}\n\n"
            "This link can also be forwarded to you via WhatsApp or SMS.\n"
        )
    else:
        subject = "Your race organiser login link"
        body = (
            f"Hi {user_name or ''},\n\n"
            f"Use this link to log in to your organiser account:\n\n"
            f"{magic_link_url}\n"
        )
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user_email])
