# Deployment

## Local development
- Postgres + Redis via `docker-compose up -d` (Redis reserved for Phase 3+).
- API: `uvicorn app.main:app` (python3.10 venv). Migrate with `alembic upgrade head`.
- Web: `npm run dev` in `apps/web`.

See the repo `README.md` for the exact commands and the Colima/credential note.

## Production (future)
- Containerise `apps/api` and `apps/web`; run Alembic migrations on release.
- Set all secrets via environment (`.env.example` lists them); never commit `.env`.
- Put Postgres on managed storage with backups; front the API with TLS.
- Swap the local storage driver for S3 (`STORAGE_DRIVER=s3`).
- Before any production deploy, pin `next` to the latest patched release and
  re-run `npm audit` (see README "Known limitations").
