"""
Idempotent bootstrap for a fresh deployment (e.g. a demo host): a platform
superuser (Django Admin access to everything) and, optionally, a demo
Organisation + organiser account so the app is immediately walkable
without hand-editing the database.

Safe to run on every deploy — driven entirely by env vars, and a no-op
for anything already created (just refreshes the password so you can
rotate it by changing the env var and redeploying).
"""

import os

from django.core.management.base import BaseCommand

from accounts.models import Organisation, OrganisationMember, User


class Command(BaseCommand):
    help = "Create/update a superuser and optional demo organisation from env vars."

    def handle(self, *args, **options):
        superuser_email = os.environ.get("DJANGO_SUPERUSER_EMAIL")
        superuser_password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")

        if superuser_email and superuser_password:
            user, created = User.objects.get_or_create(
                email__iexact=superuser_email,
                defaults={"email": superuser_email, "is_staff": True, "is_superuser": True},
            )
            user.is_staff = True
            user.is_superuser = True
            user.set_password(superuser_password)
            user.save()
            self.stdout.write(
                self.style.SUCCESS(f"{'Created' if created else 'Updated'} superuser {superuser_email}")
            )
        else:
            self.stdout.write("DJANGO_SUPERUSER_EMAIL/PASSWORD not set — skipping superuser.")

        demo_org_name = os.environ.get("DEMO_ORG_NAME")
        demo_organiser_email = os.environ.get("DEMO_ORGANISER_EMAIL")
        demo_organiser_password = os.environ.get("DEMO_ORGANISER_PASSWORD")

        if demo_org_name and demo_organiser_email and demo_organiser_password:
            slug = os.environ.get("DEMO_ORG_SLUG") or demo_org_name.lower().replace(" ", "-")
            org, _ = Organisation.objects.get_or_create(
                slug=slug,
                defaults={"name": demo_org_name, "billing_email": demo_organiser_email},
            )
            organiser, created = User.objects.get_or_create(
                email__iexact=demo_organiser_email,
                defaults={"email": demo_organiser_email, "is_staff": True},
            )
            organiser.is_staff = True
            organiser.set_password(demo_organiser_password)
            organiser.save()
            OrganisationMember.objects.get_or_create(
                organisation=org, user=organiser, defaults={"role": OrganisationMember.Role.OWNER}
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"{'Created' if created else 'Updated'} demo organiser {demo_organiser_email} @ {org.name}"
                )
            )
        else:
            self.stdout.write("DEMO_ORG_NAME/DEMO_ORGANISER_EMAIL/DEMO_ORGANISER_PASSWORD not set — skipping demo org.")
