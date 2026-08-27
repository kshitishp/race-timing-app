"""
Session-token auth: a JWT issued after a magic link is consumed (§9 — "a
long-lived signed session token exchanged from the magic link, so the
volunteer stays logged in for the duration of the event without needing
connectivity to re-authenticate. JWT verification is stateless, so expiry
can be checked entirely client-side; revocation is only checked the next
time the device is online.")
"""

import jwt
from django.conf import settings
from django.utils import timezone
from rest_framework import authentication, exceptions

from accounts.models import User

JWT_ALGORITHM = "HS256"


def issue_session_token(user, race=None, checkpoint=None):
    now = timezone.now()
    payload = {
        "user_id": user.id,
        "race_id": race.id if race else None,
        "checkpoint_id": checkpoint.id if checkpoint else None,
        "iat": int(now.timestamp()),
        "exp": int((now + timezone.timedelta(hours=settings.SESSION_TOKEN_TTL_HOURS)).timestamp()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_session_token(token):
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[JWT_ALGORITHM])


def build_magic_link_url(raw_token):
    return f"{settings.FRONTEND_BASE_URL.rstrip('/')}/auth/consume?token={raw_token}"


class SessionTokenAuthentication(authentication.BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).decode("utf-8")
        if not header or not header.startswith(f"{self.keyword} "):
            return None
        raw_token = header[len(self.keyword) + 1 :].strip()
        try:
            payload = decode_session_token(raw_token)
        except jwt.ExpiredSignatureError:
            raise exceptions.AuthenticationFailed("Session token expired.")
        except jwt.InvalidTokenError:
            raise exceptions.AuthenticationFailed("Invalid session token.")

        try:
            user = User.objects.get(pk=payload["user_id"], is_active=True)
        except User.DoesNotExist:
            raise exceptions.AuthenticationFailed("User not found.")

        auth_context = {
            "race_id": payload.get("race_id"),
            "checkpoint_id": payload.get("checkpoint_id"),
        }
        return (user, auth_context)
