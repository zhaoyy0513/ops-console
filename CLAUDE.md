# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

FastAPI service (`prime-monitor-platform`), currently a bare scaffold: all routes live in `main.py`. Python 3.13, dependencies managed with **uv** (fastapi, uvicorn).

## Commands

```bash
uv sync                            # install dependencies into .venv
uv run uvicorn main:app --reload   # dev server (http://127.0.0.1:8000, docs at /docs)
uv add <package>                   # add a dependency (updates pyproject.toml + uv.lock)
```

No tests, linting, or CI exist yet.

## Conventions

- All endpoints are `async def` route handlers on the module-level `app` in `main.py`. Keep new routes there until the project grows a package structure.
