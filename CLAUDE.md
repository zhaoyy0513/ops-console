# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Internal Ops & Diagnostics Platform ("Ops Console") — lightweight, site-centric diagnostics for servers (SSH, read-only), Redis (the only writable resource), ActiveMQ Artemis (Jolokia) and robots (HTTP API). No user system, no login, no RBAC.

**Status**: V1 complete — all 33 tasks in `tasks/todo.md` checked, PRD §33 acceptance 1-18 verified. Current phase: UI upgrade per `docs/ui-upgrade-design.md` (design tokens, dark mode, vue-bits animations).

Monorepo layout:

- `backend/` — FastAPI (Python 3.13, managed with **uv**). Entry: `backend/app/main.py`.
- `frontend/` — Vue 3 + TypeScript + Vite (naive-ui, pinia, vue-router, axios, echarts, vue-i18n zh/en, codemirror).
- `deploy/` — `Dockerfile.nginx` + `nginx.conf` (ops-nginx serves frontend dist, proxies `/api`).
- `scripts/e2e_live.py` — live E2E against real site resources (needs `.env`).
- `tasks/plan.md` / `tasks/todo.md` — implementation plan and task checklist.
- `docs/` — `draft.md` (raw notes), `prd-tech-design.md` (v0.1), `prd-tech-design-v0.2.md` (**baseline PRD**), `ui-upgrade-design.md` (current UI phase).

## Commands

```bash
# Backend
uv sync                                                       # install deps into .venv
uv run --env-file .env python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000  # dev server (http://127.0.0.1:8000, docs at /docs)
uv run pytest                                                 # run backend tests (19 files, fakeredis — no live services)
uv add <package>                                              # add a dependency

# Frontend (run inside frontend/)
npm install              # first time
npm run dev              # dev server (http://localhost:5173, /api proxied to :8000)
npm run build            # production build (vue-tsc + vite)
npx vitest run           # frontend tests (5 files)

# Live E2E — script targets http://127.0.0.1:8123, so start the backend on that port first:
uv run --env-file .env uvicorn backend.app.main:app --port 8123
uv run --env-file .env python scripts/e2e_live.py

# Deploy (single command; reuses existing Redis via OPS_REDIS_URL, ops-nginx on ${OPS_PORT:-8090})
docker compose up -d --build

cd frontend && npm run dev -- --host 0.0.0.0 
```

Env vars live in `.env` (gitignored) — one file shared by local dev (`--env-file .env`) and Compose (auto-read). Template: `.env.example`. E2E-only vars (ARTEMIS_*, SERVER_*) are optional.

Gotcha: if `uv run uvicorn ...` fails with "uv trampoline failed to canonicalize script path", run `uv sync --reinstall-package uvicorn`, or use `uv run python -m uvicorn backend.app.main:app`.

Gotcha (this machine): do NOT pass `--reload` — StatReload wedges on Windows when the repo is being touched (e.g. PyCharm indexing): the listening socket vanishes while the worker process survives, `Ctrl+C` stops working, and the port stays unusable until both PIDs are killed. Start without `--reload`.

## Architecture

### Module registry (both ends — the core extension mechanism)

- Backend: each feature lives in `backend/app/modules/<name>/` (`api.py` + `service.py` + `provider.py`), exposing `register_module(app)`. `backend/app/modules/__init__.py::register_all` imports the list. `main.py` must stay clean (app creation, error handlers, request-id middleware only) — never import a concrete module there.
- Frontend: `frontend/src/modules/<name>/` with `defineOpsModule({...})`, registered in `src/modules/index.ts`. Layout sidebar and router (`/console/site/:siteId/:moduleId`) are generated from the registry.
- Modules: `sites, server, redis, mq, robot, overview, audit, testconn, ssh, database` (last one is the extension-mechanism demo — fake metrics).

**Adding a module = new directory + one line in the registry list, on each end. Do not modify main.py / layout / router / stores.**

### Non-negotiable rules (from PRD / plan.md)

- **Two Redis dimensions, never mixed**: platform Redis (`OPS_REDIS_URL`, held by `core/redis.py` — config, cache, locks, oplog) vs monitored business Redis (connections created per-site-config by the redis module's provider). Separate connection factories, always.
- **Adapter-first**: business/services layer never touches asyncssh/redis-py/httpx directly — only module providers.
- **Server is read-only**: SSH diagnostics use a fixed internal command whitelist; no user-facing command input, no shell, no file ops.
- **Redis is the only writable resource**: SCAN only (never `KEYS *`); FLUSHDB/FLUSHALL/CONFIG/SHUTDOWN/SCRIPT FLUSH/EVAL are unreachable by construction; every write op records an oplog entry (`core/oplog.py`, LPUSH+LTRIM 1000).
- **All external calls**: timeout + max 1-2 retries + per-resource-type semaphore (see `shared/timeout.py`, `shared/concurrency.py`). Errors go through the unified envelope (`shared/errors.py` OpsError) — a failing resource renders Unknown, never a 500.
- **Passwords**: never echoed in API responses; submitting an empty password field means "keep existing".
- **Caching**: short TTL (~5s) + Redis lock request-coalescing for SSH/MQ/Redis/Robot queries; on-demand queries, 30s lightweight background health check (APScheduler). No WebSockets, no long-lived connections.
- **Frontend i18n**: all user-facing strings go through `src/i18n/index.ts` (zh + en keys). Never hardcode Chinese in templates.

### Tests

- Backend: `backend/tests/` — pytest + fakeredis (conftest), covers parsers, diagnosis thresholds, cache coalescing, APIs (sites/resources/redis/mq/robot/server/testconn/export-import), oplog, registry.
- Frontend: vitest + happy-dom — `registry.test.ts`, `stores/site.test.ts`, `CountdownConfirm.test.ts`, `ResourceTestButton.test.ts`, `SshView.test.ts`.
- Run both suites before considering any change done: `uv run pytest` and `cd frontend && npx vitest run`.
