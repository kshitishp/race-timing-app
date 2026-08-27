# Deploying a demo

Backend → **Render** (free web service + free Postgres). Frontend → **Vercel**
(you already have an account). Both have generous free tiers and give you a
real, persistent HTTPS URL — required anyway for camera access
(`getUserMedia`) and PWA install.

Two things worth knowing going in:

- Render's free web service **sleeps after ~15 min idle** and takes
  30-60s to wake on the next request — fine for a demo, just don't be
  surprised by the first load. Its free Postgres **expires after 90
  days** (plenty for a demo; recreate the database if you need it longer).
- This deploy uses **Postgres**, not the MySQL the blueprint names for
  production (§7) — free managed MySQL isn't really available and
  `mysqlclient` needs system libraries most PaaS free tiers don't ship.
  Nothing else changes: `settings.py` already picks the DB engine from
  `DATABASE_URL`, so this is purely a hosting-convenience swap (see
  `backend/requirements-mysql.txt` if you later self-host with real MySQL).

## 1. Backend — Render

1. Push this branch to GitHub (already done if you're reading this from
   the repo).
2. In the Render dashboard: **New → Blueprint**, pick this repo and the
   `dev` branch. Render reads `render.yaml` at the repo root and
   provisions the web service + a free Postgres database together.
3. When prompted for env vars, set at minimum:
   - `DJANGO_SUPERUSER_EMAIL` / `DJANGO_SUPERUSER_PASSWORD` — your Django
     Admin login.
   - Optionally `DEMO_ORG_NAME`, `DEMO_ORGANISER_EMAIL`,
     `DEMO_ORGANISER_PASSWORD` — bootstraps a demo `Organisation` +
     organiser account (not a superuser) so you can walk the real
     organiser flow immediately.
   - Leave `FRONTEND_BASE_URL` blank for now — you'll set it in step 3
     below, once you have a Vercel URL.
4. Deploy. First build takes a few minutes (installs deps, runs
   `collectstatic`, `migrate`, and `seed_admin` — see
   `backend/accounts/management/commands/seed_admin.py`).
5. Once live, note the backend URL, e.g. `https://race-timing-backend.onrender.com`.
   Confirm it's up: `https://<that-url>/admin/` should show the Django
   Admin login page.

Don't have a Render account yet? Sign up free at render.com — no card
required for the free tier.

## 2. Frontend — Vercel

1. In the Vercel dashboard: **New Project**, import this repo.
2. Set **Root Directory** to `frontend` if that field is editable for you
   (click any "Edit" link next to it — it's sometimes read-only until
   you do). Vercel then auto-detects Vite (build command `npm run
   build`, output `dist`) and uses `frontend/vercel.json` for the SPA
   rewrite React Router needs (so `/scan` and `/auth/consume` don't 404
   on refresh) while leaving the PWA's `sw.js`/manifest/icons served as
   real files.

   **If Root Directory won't accept a value** (a known Vercel UI quirk on
   some accounts), skip it — leave Root Directory as the repo root and
   deploy as-is. The root-level `vercel.json` handles everything instead
   (`cd frontend && npm install && npm run build`, output
   `frontend/dist`, plus the same SPA rewrite) — no dashboard field
   needed.
3. Add an environment variable: `VITE_API_BASE_URL` =
   `https://<your-render-url>.onrender.com/api`. (Vite bakes env vars in
   at build time, so this must be a Vercel project env var, not just
   `frontend/.env` — that file isn't committed.)
4. Deploy. Note the resulting URL, e.g. `https://race-timing-app.vercel.app`.

## 3. Wire them together

Back in Render, open the web service's **Environment** tab and set
`FRONTEND_BASE_URL` to your Vercel URL from step 2 (no trailing slash).
Save — Render restarts the service automatically (no rebuild needed).
This is what the backend uses to build the magic-link URLs it emails to
volunteers/organisers, so they land on the right frontend.

## 4. Try it

1. Visit `https://<render-url>/admin/`, log in with your superuser (or
   demo organiser) credentials.
2. Create a `Race`, some `Checkpoints`, a `Participant` (this fires the
   QR-code email — see "Email" below), and invite a `Volunteer` — either
   via Admin's `RaceVolunteers`, or `POST /api/races/:id/volunteers`
   (returns a `magic_link_url` in the JSON response either way).
3. Open that magic-link URL (`https://<vercel-url>/auth/consume?token=...`)
   on a phone — it logs the volunteer in, caches the roster, and lands on
   the scan screen. Camera scanning needs HTTPS, which Vercel gives you
   by default.

### Email

The default `DJANGO_EMAIL_BACKEND` is the console backend — emails don't
actually deliver, they're printed to Render's **Logs** tab. That's often
enough for a demo (grab the magic-link URL from the API response or the
log line instead of an inbox). To get real email delivery, add these env
vars in Render (Gmail is the fastest zero-new-signup option — create an
[App Password](https://myaccount.google.com/apppasswords) on the sending
account, not your regular password):

```
DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=true
EMAIL_HOST_USER=youraddress@gmail.com
EMAIL_HOST_PASSWORD=<the app password>
DEFAULT_FROM_EMAIL=youraddress@gmail.com
```

## Redeploying

Both Render and Vercel redeploy automatically on push to the branch
you connected. `seed_admin` re-runs on every Render deploy — it's
idempotent (updates the password if you change the env var, does nothing
otherwise).

## Alternative: quick local tunnel (no accounts, temporary)

For a same-day, no-setup demo instead: run both dev servers locally
(`python manage.py runserver`, `npm run dev`) and expose the frontend
with a tunnel that gives you HTTPS, e.g. `npx localtunnel --port 5173` or
`cloudflared tunnel --url http://localhost:5173`. Set
`VITE_API_BASE_URL` to a similarly tunneled backend URL (or tunnel both).
Only live while your machine + tunnel are running, but zero deployment
work.
