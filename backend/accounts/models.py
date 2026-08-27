import hashlib
import secrets

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone


class Organisation(models.Model):
    """The tenant. Every Race (and everything hanging off it) belongs to
    exactly one Organisation (§8, §10)."""

    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    billing_email = models.EmailField()
    stripe_customer_id = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Anyone who logs in — organiser staff and volunteers share this
    table; role is contextual, assigned via OrganisationMember /
    RaceVolunteer join tables (§8)."""

    email = models.EmailField(unique=True)
    name = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=32, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.email


class OrganisationMember(models.Model):
    """Organiser-side roles (§8)."""

    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        STAFF = "staff", "Staff"

    organisation = models.ForeignKey(
        Organisation, on_delete=models.CASCADE, related_name="members"
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="organisation_memberships")
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.STAFF)

    class Meta:
        unique_together = ("organisation", "user")

    def __str__(self):
        return f"{self.user.email} @ {self.organisation.name} ({self.role})"


def _generate_raw_token():
    return secrets.token_urlsafe(32)


def _hash_token(raw_token):
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


class MagicLinkQuerySet(models.QuerySet):
    def valid(self):
        return self.filter(used_at__isnull=True, expires_at__gt=timezone.now())


class MagicLink(models.Model):
    """Issued login tokens (§8). Kept as their own table for auditability
    and to allow several outstanding links per user."""

    class Purpose(models.TextChoices):
        ORGANISER_LOGIN = "organiser_login", "Organiser login"
        VOLUNTEER_LOGIN = "volunteer_login", "Volunteer login"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="magic_links")
    token_hash = models.CharField(max_length=64, unique=True)
    purpose = models.CharField(max_length=32, choices=Purpose.choices)
    # Volunteer links are scoped to a race. Declared as a lazy string ref
    # to avoid a circular import with races.models.
    race = models.ForeignKey(
        "races.Race", on_delete=models.CASCADE, null=True, blank=True, related_name="magic_links"
    )
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = MagicLinkQuerySet.as_manager()

    @classmethod
    def issue(cls, user, purpose, race=None, ttl_minutes=60):
        raw_token = _generate_raw_token()
        link = cls.objects.create(
            user=user,
            token_hash=_hash_token(raw_token),
            purpose=purpose,
            race=race,
            expires_at=timezone.now() + timezone.timedelta(minutes=ttl_minutes),
        )
        return link, raw_token

    @classmethod
    def consume(cls, raw_token):
        """Return the MagicLink for a valid, unused, unexpired raw token
        and mark it used, or None if the token doesn't resolve."""
        token_hash = _hash_token(raw_token)
        link = cls.objects.valid().filter(token_hash=token_hash).select_related("user", "race").first()
        if link is None:
            return None
        link.used_at = timezone.now()
        link.save(update_fields=["used_at"])
        return link

    def __str__(self):
        return f"{self.purpose} link for {self.user.email}"
