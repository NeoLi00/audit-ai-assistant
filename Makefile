SHELL := /bin/bash
BACKEND_DIR := backend
FRONTEND_DIR := frontend
BACKEND_PORT ?= 8000
FRONTEND_PORT ?= 5173

.PHONY: local-env postgres-env dev-services backend-install backend-install-mineru backend-install-local-models backend-dev frontend-install frontend-dev migrate seed worker test lint

local-env:
	cp .env.local.example .env
	@echo "Wrote .env for no-Docker local SQLite mode."

postgres-env:
	cp .env.example .env
	@echo "Wrote .env for Docker/PostgreSQL mode."

dev-services:
	@command -v docker >/dev/null 2>&1 || (echo "Docker CLI was not found. Install Docker Desktop, or run 'make local-env' and skip dev-services for SQLite local mode."; exit 1)
	docker compose up -d postgres redis minio qdrant

backend-install:
	cd $(BACKEND_DIR) && python3 -m venv .venv && . .venv/bin/activate && pip install --upgrade pip && pip install -e ".[dev]"

backend-install-mineru:
	cd $(BACKEND_DIR) && . .venv/bin/activate && pip install -e ".[mineru]"

backend-install-local-models:
	cd $(BACKEND_DIR) && . .venv/bin/activate && pip install -e ".[local-models]"

backend-dev:
	@python3 -c "import socket,sys; s=socket.socket(); sys.exit(1 if s.connect_ex(('127.0.0.1', int('$(BACKEND_PORT)'))) == 0 else 0)" || (echo "Port $(BACKEND_PORT) is already in use. Stop the existing backend or run BACKEND_PORT=8001 make backend-dev."; exit 1)
	cd $(BACKEND_DIR) && . .venv/bin/activate && uvicorn app.main:app --reload --host 0.0.0.0 --port $(BACKEND_PORT)

frontend-install:
	cd $(FRONTEND_DIR) && npm install

frontend-dev:
	@python3 -c "import socket,sys; s=socket.socket(); sys.exit(1 if s.connect_ex(('127.0.0.1', int('$(FRONTEND_PORT)'))) == 0 else 0)" || (echo "Port $(FRONTEND_PORT) is already in use. Stop the existing frontend or run FRONTEND_PORT=5174 make frontend-dev."; exit 1)
	cd $(FRONTEND_DIR) && npm run dev -- --host 0.0.0.0 --port $(FRONTEND_PORT)

migrate:
	cd $(BACKEND_DIR) && . .venv/bin/activate && alembic upgrade head

seed:
	cd $(BACKEND_DIR) && . .venv/bin/activate && python -m app.db.seed

worker:
	cd $(BACKEND_DIR) && . .venv/bin/activate && celery -A app.services.tasks.celery_app.celery_app worker --loglevel=info

test:
	cd $(BACKEND_DIR) && . .venv/bin/activate && pytest
	cd $(FRONTEND_DIR) && npm run build

lint:
	cd $(BACKEND_DIR) && . .venv/bin/activate && ruff check app
	cd $(FRONTEND_DIR) && npm run lint
