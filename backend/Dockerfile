# 后端镜像：uv 管理依赖（PRD §25.1），构建上下文 = 仓库根目录
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/app/.venv

# 先装依赖（层缓存友好）
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# 再拷代码
COPY backend/ ./backend/

EXPOSE 8000
CMD ["/app/.venv/bin/uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
