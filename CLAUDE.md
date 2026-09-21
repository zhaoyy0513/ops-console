# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Internal Ops & Diagnostics Platform ("Ops Console"). Monorepo:

- `backend/` — FastAPI service (`prime-monitor-platform`), Python 3.13, managed with **uv**. App entry: `backend/app/main.py`.
- `frontend/` — Vue 3 + TypeScript + Vite (naive-ui, pinia, vue-router, axios, echarts).
- `tasks/plan.md` / `tasks/todo.md` — implementation plan and task checklist (source of truth for what to build next).

## Commands

```bash
# Backend
uv sync                                        # install deps into .venv
uv run --env-file dev.env uvicorn backend.app.main:app --reload   # dev server (http://127.0.0.1:8000, docs at /docs)
uv run pytest                                  # run backend tests
uv add <package>                               # add a dependency

# Frontend
cd frontend && npm install                     # first time
cd frontend && npm run dev                     # dev server (http://localhost:5173)
cd frontend && npm run build                   # production build
cd frontend && npx vitest run                  # frontend tests
```

Note: if `uv run uvicorn ...` fails with "uv trampoline failed to canonicalize script path", run `uv sync --reinstall-package uvicorn` (stale trampoline from an older uv), or use `uv run python -m uvicorn backend.app.main:app`.

Tests (pytest / vitest) are configured but no test files exist yet.

## Conventions

- Backend routes are `async def` handlers on the module-level `app` in `backend/app/main.py`, until the module registry lands (Task 03 in `tasks/todo.md`); after that, each feature lives in `backend/app/modules/<name>/` and registers via one line.
- Follow `tasks/plan.md` architecture decisions (module registry front & back, adapter-first, platform Redis via `OPS_REDIS_URL` isolated from business Redis).
