# Moving the database off your PC — plan (revisit anytime)

_Last updated: 2026-09-16_

**Goal:** stop the data depending on your Mac being on. Right now the database runs
in Docker on your machine — if the Mac is off, asleep, or crashes, the data is
unreachable and at risk. We move it to a **managed cloud database** that runs 24/7,
is backed up automatically, and is reachable from anywhere.

---

## Important: two different "not dependent on my PC"

There are two layers. Be clear which you want — they are separate steps.

1. **The data is safe & always available (this document).**
   Move the **database** to a managed cloud Postgres. The data then lives in the
   cloud, backed up, independent of your Mac. **The app (Benfieg, the screens) still
   runs on your Mac** for now — but the data behind it is safe and shared.

2. **The whole system is online 24/7 (a later step).**
   Also host the **app itself** (the backend + the website) in the cloud, so staff
   can open it from any device even when your Mac is off. This is a follow-on
   project — see the last section. Do step 1 first; it's the foundation.

Doing step 1 alone already means: your data is never lost if the Mac dies, and when
we later host the app, it just points at the same cloud database.

---

## The good news: the app is already ready for this

The app reads its database location from one setting, `DATABASE_URL`, in the `.env`
file. Moving to the cloud is essentially **changing that one line** to the cloud
database's address and running the migrations. No code rewrite.

---

## Step-by-step (about 30–45 minutes)

### 1. Create a managed Postgres database
Pick one provider and create a free Postgres database. **My recommendation: Neon**
(simplest, generous free tier, standard Postgres).

- **Neon** — https://neon.tech — serverless Postgres, free to start. _Recommended._
- **Supabase** — https://supabase.com — Postgres with a nice dashboard + backups UI.
- **Railway / Render** — https://railway.app / https://render.com — simple paid Postgres.
- **AWS RDS / Google Cloud SQL** — most robust, more setup and cost (later, if needed).

> You'll create the account and database yourself (I can't create accounts or handle
> your passwords). Everything after that, I've prepared.

When it's created, the provider gives you a **connection string** that looks like:
```
postgresql://USER:PASSWORD@ep-xxxx.eu-central-1.aws.neon.tech/dbname?sslmode=require
```

### 2. Make it work with our app
Our app uses the `psycopg` driver, so change the scheme from `postgresql://` to
`postgresql+psycopg://` and keep `?sslmode=require` (cloud databases require SSL):
```
postgresql+psycopg://USER:PASSWORD@ep-xxxx.../dbname?sslmode=require
```

### 3. Put it in your .env (never commit this)
In the repo root `.env`, replace the `DATABASE_URL=` line with the cloud one above.
Keep the old local line commented out so you can switch back while testing:
```
# DATABASE_URL=postgresql+psycopg://digitaltwin:digitaltwin@localhost:5432/digitaltwin
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@ep-xxxx.../dbname?sslmode=require
```

### 4. Create the tables on the cloud database
From the repo root:
```
make migrate
```
This runs the migrations and builds the full schema on the new cloud database.

### 5. Move your existing data (only if you already have real data)
If the local database only has demo/seed data, skip this and just run `make seed`.
If you have **real** data to keep, copy it up with the backup script:
```
apps/api/scripts/backup_db.sh              # dumps the LOCAL db to a file
apps/api/scripts/restore_db.sh <dumpfile>  # restores it into the cloud db (uses DATABASE_URL)
```
(The scripts use the Postgres tools inside your existing Docker container, so you
don't need to install anything.)

### 6. Restart and verify
Restart the API, open the app, confirm your data is there. Done — the data now
lives in the cloud.

---

## Backups
- **Managed providers back up automatically** (point-in-time restore). On Neon/Supabase
  this is on by default — check the dashboard for the retention window.
- **Manual backup any time:** `apps/api/scripts/backup_db.sh` writes a dated dump file
  you can keep. Run it before big changes.

## Cost
- Free tiers are enough to start. They may "sleep" when idle and wake on first use
  (a second's delay) — fine for a business app.
- When you rely on it daily with real data, move to the small paid tier (~$19/mo on
  Neon's Launch plan, similar on Supabase) for guaranteed backups and no cold starts.

---

## Later: host the app itself (step 2 — makes it 24/7 for everyone)

Once the database is in the cloud, host the two app parts so it works with the Mac off:
- **Backend (FastAPI):** Render, Railway, or Fly.io — point its `DATABASE_URL` at the
  same cloud database.
- **Frontend (Next.js website):** Vercel — point `NEXT_PUBLIC_API_BASE_URL` at the
  hosted backend's address.
- Then staff open a normal web address from any device, anytime.

This is a separate project; when you're ready, tell me and I'll prepare it the same
way (plan + steps + config), and you create the accounts.

---

## What I've prepared on the code side
- The app already switches databases from the single `DATABASE_URL` setting.
- Added connection resilience for cloud databases (drops stale idle connections).
- Added `apps/api/scripts/backup_db.sh` and `restore_db.sh`.
- `.env.example` shows a commented cloud-database example line.

## What needs you
- [ ] Create the managed Postgres (Neon recommended) and copy its connection string.
- [ ] Paste it into `.env` as `DATABASE_URL` (with `+psycopg` and `?sslmode=require`).
- [ ] Run `make migrate` (and `make seed` or the restore script).
- [ ] Decide later whether to also host the app for 24/7 access (step 2).
