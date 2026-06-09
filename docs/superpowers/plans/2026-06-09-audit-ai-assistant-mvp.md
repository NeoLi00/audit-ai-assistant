# Audit AI Assistant MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable local MVP for a university audit AI assistant with mock model providers, document parsing, RAG citations, and an Ant Design frontend.

**Architecture:** Create a monorepo with FastAPI/SQLAlchemy backend, React/Vite frontend, Docker Compose infrastructure, optional MinIO/Qdrant/OpenSearch integrations, and graceful local fallbacks. The backend owns parsing, storage, indexing, permission filtering, and model gateway orchestration; the frontend provides the ima-style shell and the requested pages.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.x, Alembic, Celery, PostgreSQL, Redis, MinIO, Qdrant, React, TypeScript, Vite, Ant Design.

---

### Task 1: Project Shell

**Files:**
- Create: `.env.example`, `docker-compose.yml`, `Makefile`, `README.md`, `.gitignore`
- Create: `backend/pyproject.toml`, `backend/alembic.ini`, `frontend/package.json`, `frontend/vite.config.ts`

- [x] Create root configuration and local service compose files.
- [x] Keep all paths relative and cross-platform for macOS and Ubuntu.

### Task 2: Backend Core

**Files:**
- Create: `backend/app/core/config.py`, `backend/app/core/security.py`, `backend/app/db/models.py`, route and schema modules.
- Test: `backend/app/tests/test_health.py`, `backend/app/tests/test_mock_embedding.py`

- [ ] Write tests for health and deterministic mock embeddings.
- [ ] Implement settings, SQLAlchemy models, auth seed users, and FastAPI app startup.

### Task 3: Document Processing and RAG

**Files:**
- Create: parser modules, storage wrapper, chunker, retriever, fusion, prompt builder, citation builder, answer service.
- Test: `backend/app/tests/test_chunker.py`, parser fallback tests.

- [ ] Write tests for chunking, OCR fallback, and RRF ranking.
- [ ] Implement parsing for Word, Excel, PDF, images with optional OCR/LibreOffice fallbacks.
- [ ] Implement mock embedding, vector indexing fallback, keyword fallback, prompt construction, and citations.

### Task 4: Frontend

**Files:**
- Create: frontend API clients, layout, pages, components, and global CSS.

- [ ] Implement ima-style app shell with sidebar, top title area, white cards, grey background, and fixed chat input.
- [ ] Implement Home, Chat, Knowledge Base, Document Detail, History, Settings, and Admin pages.

### Task 5: Verification

**Commands:**
- `cd backend && python3 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]" && pytest`
- `cd frontend && npm install && npm run build`

- [ ] Run backend tests and fix failures.
- [ ] Run frontend build and fix failures.

