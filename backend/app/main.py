from fastapi import FastAPI
from starlette.requests import Request

from backend.app.core.config import settings
from backend.app.core.logging import new_request_id, setup_logging
from backend.app.core.redis import get_platform_redis
from backend.app.core.request_info import set_caller
from backend.app.modules import register_all
from backend.app.shared.errors import OpsError, ops_error_handler, unhandled_error_handler

setup_logging(settings.log_level)

# 容器低 pids 上限防线：asyncssh 每次 connect 都经默认线程池做 DNS 解析，
# 默认池上限 min(32, cpu+4)——容器 cgroup pids / ulimit -u 打满时 Python 抛
# "can't start new thread"（线上表现为所有 SSH 接口 500）。包一层惰性池：只有
# 真提交任务才起线程，且总量封顶在 OPS_THREADPOOL_MAX（默认 8，远小于
# 32）——SSH 信号量已限并发 ≤8+4，8 足够；解析只在 connect 阶段（毫秒级）。
import asyncio
import concurrent.futures
import functools
import os

_POOL = concurrent.futures.ThreadPoolExecutor(
    max_workers=int(os.environ.get("OPS_THREADPOOL_MAX", "8")),
    thread_name_prefix="opsio",
)


class _BoundedExecutor(concurrent.futures.Executor):
    """run_in_executor 门面：把任务提交到上面的小池（替代 loop 默认池）。"""

    def submit(self, fn, /, *args, **kwargs):
        return _POOL.submit(fn, *args, **kwargs)


_bounded_executor = _BoundedExecutor()
_orig_run_in_executor = asyncio.BaseEventLoop.run_in_executor


@functools.wraps(_orig_run_in_executor)
async def _patched_run_in_executor(self, executor, func, *args):
    # executor=None（默认池）或 ThreadPoolExecutor 实例 → 换成小池；
    # 想用其他自定义 executor 的调用方保持原样
    if executor is None or isinstance(executor, concurrent.futures.ThreadPoolExecutor):
        return await _orig_run_in_executor(self, _bounded_executor, func, *args)
    return await _orig_run_in_executor(self, executor, func, *args)


asyncio.BaseEventLoop.run_in_executor = _patched_run_in_executor


app = FastAPI()
app.add_exception_handler(OpsError, ops_error_handler)
app.add_exception_handler(Exception, unhandled_error_handler)


def _caller_ip(request: Request) -> str:
    """调用者 IP：ops-nginx 反代后 client.host 是容器 IP，真实来源在转发头里。
    取 X-Forwarded-For 第一跳（客户端最初 IP），退 X-Real-IP，再退直连地址。"""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "-")


@app.middleware("http")
async def request_context(request: Request, call_next):
    """请求级日志字段（PRD §29）：request_id 透传响应头，站点随路径。
    同时落调用者上下文（IP + 操作人别名），oplog 记录时自动读取。"""
    rid = new_request_id()
    path_parts = request.url.path.split("/")
    site_id = path_parts[3] if len(path_parts) > 3 and path_parts[1] == "api" and path_parts[2] == "sites" else "-"
    set_caller(_caller_ip(request), request.headers.get("x-ops-user") or "-")
    import loguru

    with loguru.logger.contextualize(request_id=rid, site_id=site_id, resource_id="-"):
        response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response


register_all(app)


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/hello/{name}")
async def say_hello(name: str):
    return {"message": f"Hello {name}"}


@app.get("/api/health")
async def health():
    try:
        await get_platform_redis().ping()
        return {"status": "ok", "redis": True}
    except Exception:
        return {"status": "degraded", "redis": False}
