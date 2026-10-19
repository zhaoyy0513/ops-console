# 后端镜像：uv 管理依赖（PRD §25.1），构建上下文 = 仓库根目录
FROM python:3.13-slim-bookworm

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/app/.venv

# asyncssh 在每次 connect 时把 DNS 解析丢进默认线程池（min(32, cpu+4)），
# 低配容器（小 cgroup pids 上限）容易在并发建连时把线程配额打满——
# 显式压小；uvicorn 自身线程极少，不受影响
ENV PYTHONASYNCIODEBUG=0
ENV OPS_THREADPOOL_MAX=8

# 先装依赖（层缓存友好）
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# 再拷代码
COPY backend/ ./backend/

EXPOSE 8000
CMD ["/app/.venv/bin/uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
