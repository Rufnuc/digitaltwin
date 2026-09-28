# Hosting DigitalTwin — going live (Neon + Render + Vercel)

_Last updated: 2026-09-28_

You are hosting **two separate businesses** — **Fidel Agric** and **Urban Builds** —
as **two completely independent copies** of the same app. Same code, but each has its
own database, its own website address, its own logins, and its own company details on
invoices. Neither can see the other's data.

> Do every "per business" step **twice** — once for Fidel Agric, once for Urban Builds.
> Use clear names so you never mix them up (e.g. `fidelagric-…` vs `urbanbuilds-…`).

Three free accounts do the work:
- **Neon** — the database (data lives here, backed up, 24/7).
- **Render** — the backend/API (the engine).
- **Vercel** — the website (what people open in the browser).

---

## Part 0 — Put the code on GitHub (once, shared by both)

The hosts deploy from a GitHub repository. Do this once; both businesses deploy from
the same repo.

1. On GitHub, create a **new private repository** (e.g. `digitaltwin`). Don't add a
   README/licence — keep it empty.
2. Back on your Mac, from the project folder, connect and push (replace the URL):
   ```bash
   git remote add origin https://github.com/<your-username>/digitaltwin.git
   git push -u origin master
   ```
   (I'll have already committed everything for you — you just push.)

Secrets are safe: `.env`, `backups/`, and `storage/` are git-ignored and never leave
your machine. All real secrets are typed into the hosts' dashboards, not the code.

---

## Part 1 — Database on Neon  *(per business)*

1. Sign up at **neon.tech** (free).
2. **New Project** → name it `fidelagric` (then later `urbanbuilds`). Region: pick the
   closest (e.g. Frankfurt/EU or US-East).
3. Open **Connection Details** → copy the connection string. It looks like:
   `postgresql://user:pass@ep-xxx.eu-central-1.aws.neon.tech/neondb?sslmode=require`
4. **Change the prefix** for our driver — turn `postgresql://` into
   `postgresql+psycopg://`, and make sure it ends with `?sslmode=require`. Final:
   `postgresql+psycopg://user:pass@ep-xxx…/neondb?sslmode=require`
   Keep this string safe — it's the `DATABASE_URL` for Part 2.

You don't run any migrations by hand — the API creates all the tables automatically
the first time it starts (Part 2).

---

## Part 2 — Backend/API on Render  *(per business)*

1. Sign up at **render.com** (free), and connect your GitHub.
2. **New + → Web Service** → pick your `digitaltwin` repo.
3. Settings:
   - **Name:** `fidelagric-api` (later `urbanbuilds-api`)
   - **Root Directory:** `apps/api`
   - **Runtime/Language:** Docker (it auto-detects the `Dockerfile`)
   - **Instance type:** Free to start (upgrade to Starter ~$7/mo later for no "cold
     start" delay — see Notes).
   - **Health Check Path:** `/health`
4. **Environment variables** (Advanced → Add):
   | Key | Value |
   |-----|-------|
   | `ENVIRONMENT` | `production` |
   | `AUTH_SECRET` | click **Generate** (a long random value) |
   | `DATABASE_URL` | the Neon string from Part 1 |
   | `AI_PROVIDER` | `rule_based` |
   | `ASSISTANT_ALLOW_WRITES` | `false` |
   | `WHISPER_MODEL` | *(leave empty)* |
   | `MARKET_DATA_PROVIDER` | `live` |
   | `AISSTREAM_API_KEY` | your aisstream key (optional; enables the shipping monitor) |
   | `OWNER_EMAIL` | the owner login for this business, e.g. `owner@fidelagric.com` |
   | `OWNER_PASSWORD` | a strong password (min 8 chars) |
   | `OWNER_NAME` | e.g. `Fidel Agric Owner` |
   | `CORS_ORIGINS` | *(leave blank for now — you'll set it in Part 4)* |
5. **Create Web Service.** First deploy takes a few minutes. When it's live, note the
   URL, e.g. `https://fidelagric-api.onrender.com`. Visit `…/health` — you should see
   `{"status":"ok"}`. On first boot it builds the tables and creates your owner login.

---

## Part 3 — Website on Vercel  *(per business)*

1. Sign up at **vercel.com** (free), connect GitHub.
2. **Add New → Project** → import your `digitaltwin` repo.
3. Settings:
   - **Root Directory:** `apps/web`  (click Edit → select `apps/web`)
   - Framework: **Next.js** (auto-detected)
   - **Environment Variable:**
     - `NEXT_PUBLIC_API_BASE_URL` = your Render API URL from Part 2
       (e.g. `https://fidelagric-api.onrender.com`) — no trailing slash.
4. **Deploy.** Note the site URL, e.g. `https://fidelagric.vercel.app`
   (you can rename the project so the subdomain reads nicely, or add a custom domain
   like `app.fidelagric.com` later).

---

## Part 4 — Connect them (per business)

1. Back in **Render → your API service → Environment**, set:
   - `CORS_ORIGINS` = your Vercel site URL (e.g. `https://fidelagric.vercel.app`).
     (Multiple allowed origins? separate with commas.)
2. Save — Render restarts automatically. Done.

Now open the Vercel site, sign in with the `OWNER_EMAIL` / `OWNER_PASSWORD` you set,
and finish setup for that business:
- **Settings → Company details** (name, address, phone — prints on invoices).
- **Create your warehouse(s)** (needed before receiving stock).
- **Add staff** (e.g. the salesgirl) in **Settings → Users**. First time she signs in
  from the shop laptop, approve her device in **Settings → Users → Devices**.
- Import/enter real products, suppliers, customers.

Then repeat Parts 1–4 for the second business.

---

## Part 5 — Durable file storage on Cloudflare R2  *(per business, recommended)*

Uploaded files (waybill/receipt/invoice attachments, product photos) must live in
object storage, or they're lost on every redeploy (see the note below). Cloudflare R2
is S3-compatible, has a generous free tier, and no egress fees.

1. Sign up / log in at **cloudflare.com** → **R2**. (You may need to add a card to
   activate R2; the free tier covers small usage.)
2. **Create bucket** → name it `fidelagric-files` (later `urbanbuilds-files`). Keep it
   **private** (no public access — the app streams files through the API).
3. **Manage R2 API Tokens → Create API Token** → permission **Object Read & Write**,
   scoped to that bucket. Copy the **Access Key ID**, **Secret Access Key**, and your
   **Account ID** (shown on the R2 overview; the endpoint is
   `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`).
4. In **Render → your API service → Environment**, add:
   | Key | Value |
   |-----|-------|
   | `STORAGE_DRIVER` | `r2` |
   | `R2_ACCOUNT_ID` | your Cloudflare account id |
   | `R2_ACCESS_KEY_ID` | the token's Access Key ID |
   | `R2_SECRET_ACCESS_KEY` | the token's Secret Access Key |
   | `R2_BUCKET` | `fidelagric-files` (the bucket name) |
   (Or set `R2_ENDPOINT` to the full `https://<id>.r2.cloudflarestorage.com` instead of
   `R2_ACCOUNT_ID`.)
5. Save — Render redeploys. From then on, uploads go to R2 and survive redeploys.
   Each business uses its **own bucket + token** so their files stay separate.

Leaving `STORAGE_DRIVER` unset (or `local`) keeps the old local-disk behaviour.

---

## Notes & gotchas (read once)

- **Cold starts (free tier):** Render's free API "sleeps" after ~15 min idle; the next
  request wakes it (30–60s). Fine for occasional use; upgrade to **Starter (~$7/mo)**
  per business for always-on. Neon and Vercel free tiers don't have this problem.
- **Uploaded files:** set up **Cloudflare R2 (Part 5)** so attachments are durable.
  Without it (`STORAGE_DRIVER=local`), uploaded files sit on the API's local disk,
  which Render **wipes on every redeploy** — the database records survive but the files
  would be lost. The R2 driver is built in; just set the env vars. Everything else
  (invoices, stock, payments, customers…) lives in the database and is always durable.
- **Backups:** Neon keeps automatic point-in-time backups. Your pre-launch local
  backup is in `backups/` (git-ignored).
- **Secrets:** never commit the aisstream key, DB password, or `AUTH_SECRET` — they
  live only in the Render dashboard. Rotating one = change it there and redeploy.
- **Same code, two businesses:** when you improve the app, push to GitHub once; both
  Render + Vercel projects auto-redeploy their own copy. Data stays separate.
- **Device binding & multi-laptop:** now that it's hosted, staff open the Vercel URL
  from any laptop. The salesgirl's first login from each new device is held for your
  approval (Settings → Users → Devices) — exactly the lock you asked for.
