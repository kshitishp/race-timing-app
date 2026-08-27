# Race Timing App

Offline-first race checkpoint timing, built to the [Product & Technical
Blueprint (MVP)](.). Organisers set up races, checkpoints, and participants
via Django Admin; volunteers scan/log times at checkpoints from a phone,
even with zero connectivity, and it syncs automatically once back online.

## Architecture

- **Backend:** Django + Django REST Framework + MySQL (SQLite fallback for
  local dev), Celery for async work (QR-code emails, magic-link emails).
  Organiser CRUD is a customized Django Admin — no bespoke web app.
- **Frontend:** a React + Vite PWA for volunteers — installable to a phone's
  home screen, camera QR scanning, manual-entry fallback, and an
  IndexedDB (Dexie) offline queue that syncs via an `online` listener +
  foreground timer (not the WebKit-unsupported Background Sync API).
- **Multi-tenant:** every race belongs to one `Organisation`; isolation is
  enforced in the query layer (`accounts/tenancy.py`), not the database.

See `backend/` and `frontend/` for each half.

## Backend setup

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt   # needs libmysqlclient-dev for mysqlclient;
                                   # drop that one line if you only need SQLite locally
cp .env.example .env               # defaults to SQLite + console email + eager Celery
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Admin: http://localhost:8000/admin/ — a superuser sees everything (platform
ops); an organiser (a `User` with an `OrganisationMember` row) sees only
their own organisation's races, checkpoints, participants, volunteers, and
timings.

To provision a first organiser from the shell:

```python
python manage.py shell
>>> from accounts.models import Organisation, User, OrganisationMember
>>> org = Organisation.objects.create(name="Trail Runners Co", slug="trail-runners", billing_email="billing@example.com")
>>> user = User.objects.create_user(email="organiser@example.com", password="...", is_staff=True)
>>> OrganisationMember.objects.create(organisation=org, user=user, role="owner")
```

Run the test suite (tenancy isolation, magic-link auth, idempotent
bulk-sync, duplicate detection, results compilation, billing calc):

```bash
python manage.py test
```

### Background jobs

`CELERY_TASK_ALWAYS_EAGER=true` (the `.env.example` default) runs QR-code
and magic-link emails synchronously — no Redis/worker needed for local
dev. For anything resembling production, set it to `false` and run:

```bash
celery -A config worker -l info
```

## Frontend setup (volunteer PWA)

```bash
cd frontend
npm install
cp .env.example .env   # VITE_API_BASE_URL, defaults to http://localhost:8000/api
npm run dev
```

Open on a phone (same network as the backend) to test camera scanning —
`getUserMedia` requires HTTPS or `localhost`, so for real-device testing
either use `vite --host` over a tunnel with TLS, or `npm run build && npm
run preview` behind a reverse proxy with a cert.

Volunteer flow: an organiser invites a volunteer (via Django Admin's
`RaceVolunteers`, or `POST /api/races/:id/volunteers`), which emails —
and returns, for copy/paste over WhatsApp/SMS — a magic-link URL like
`http://localhost:5173/auth/consume?token=...`. Opening it logs the
volunteer in, caches their checkpoint + race roster locally, and lands
them on the scan screen. From there, camera scans and manual entries both
queue locally first and sync automatically once online.

## API surface

See `backend/races/urls.py` and `backend/accounts/urls.py` for the full
route list — magic-link auth, race/checkpoint/participant/volunteer CRUD,
`POST /api/timings/bulk-sync` (idempotent on `client_event_id`), results +
CSV export, and read-only usage/billing records.

## What's implemented vs. deferred

Everything in the blueprint's P0 (§6) is implemented: tenant isolation,
race/checkpoint CRUD, participant creation (manual + CSV, via API and
Django Admin's import/export), QR-code-by-email on participant creation,
volunteer magic-link auth (+ shareable link), offline scan capture with
idempotent sync, duplicate-scan flagging, full audit fields on `Timing`,
results compilation, CSV export, and participant-count-based usage
metering (viewable via Django Admin — no dedicated billing UI, per the
blueprint's non-goals).

P1/P2 items (co-admin roles, live results dashboard, ITRA/UTMB export
formats, GPX/GPS features, the participant app, automated Stripe billing,
etc.) are deliberately out of scope for this build, per the blueprint's
phasing (§15) — though the schema anticipates several of them (e.g.
`Checkpoint.self_scan_code`, `Race.checkpoint_sequence_mode`,
`Profile.cross_org_sharing_consent_at`) so they don't require a later
migration to bolt on.
