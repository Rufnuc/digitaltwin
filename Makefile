# DigitalTwin — developer shortcuts
# Postgres runs in Docker; the backend uses a python3.10 venv.

PY ?= $(HOME)/.local/bin/python3.10
API := apps/api
WEB := apps/web
VENV := $(API)/.venv
DATABASE_URL ?= postgresql+psycopg://digitaltwin:digitaltwin@localhost:5432/digitaltwin
export DATABASE_URL

.PHONY: help db-up db-down api-venv api-install migrate seed api web test lint build

help:
	@echo "Targets: db-up db-down api-install migrate seed api web test lint build"

db-up:
	docker-compose up -d db

db-down:
	docker-compose down

api-venv:
	$(PY) -m venv $(VENV)

api-install: api-venv
	$(VENV)/bin/pip install -q -r $(API)/requirements.txt

migrate:
	cd $(API) && ./.venv/bin/alembic upgrade head

seed:
	cd $(API) && ./.venv/bin/python -m app.seed.demo_data --reset

api:
	cd $(API) && ./.venv/bin/uvicorn app.main:app --reload --port 8000

test:
	cd $(API) && ./.venv/bin/pytest

lint:
	cd $(API) && ./.venv/bin/ruff check .

web:
	cd $(WEB) && npm run dev

build:
	cd $(WEB) && npm run build
