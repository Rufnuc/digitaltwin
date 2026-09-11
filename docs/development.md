# Development

## Prerequisites
- Python **3.10** (this repo uses `~/.local/bin/python3.10`)
- Node 20+ / npm (verified on Node 26, npm 11)
- Docker (Postgres). On this machine the daemon is **Colima**; if `docker-compose`
  fails on a credential helper, use a clean config + the Colima socket:
  ```bash
  export DOCKER_CONFIG=/tmp/dockercfg_clean && mkdir -p $DOCKER_CONFIG && echo '{}' > $DOCKER_CONFIG/config.json
  export DOCKER_HOST=unix:///Users/$USER/.colima/default/docker.sock
  ```

## Backend
```bash
cd apps/api
~/.local/bin/python3.10 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL="postgresql+psycopg://digitaltwin:digitaltwin@localhost:5432/digitaltwin"
alembic upgrade head
python -m app.seed.demo_data --reset       # DEMO data
uvicorn app.main:app --reload --port 8000
```
Zero-infra mode: omit `DATABASE_URL` to use a local SQLite file (tables auto-created).

## Tests / lint
```bash
cd apps/api && . .venv/bin/activate
pytest            # 19 tests, run on SQLite (no Postgres needed)
ruff check .
```

## Frontend
```bash
cd apps/web
npm install
npm run dev       # http://localhost:3000
npm run build     # production build + typecheck
```
Point the UI at the API with `NEXT_PUBLIC_API_BASE_URL` in `apps/web/.env.local`.

## Layout
```
apps/{web,api}  packages/types  services/  infrastructure/{docker,database}  docs/  tests/
```
`apps/api/app` holds `core/ db/ models/ schemas/ api/ services/ seed/`.
