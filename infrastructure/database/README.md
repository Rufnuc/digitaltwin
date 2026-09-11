# Database infrastructure
Postgres is provisioned by the root `docker-compose.yml` (service `db`). Schema is
owned by Alembic migrations in `apps/api/alembic`. This directory is reserved for
future DB infra: seed SQL, backup/restore scripts, and read-replica config.
