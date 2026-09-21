from fastapi import FastAPI
from starlette.requests import Request

from backend.app.core.config import settings
from backend.app.core.logging import new_request_id, setup_logging
from backend.app.core.redis import get_platform_redis
from backend.app.modules import register_all
from backend.app.shared.errors import OpsError, ops_error_handler, unhandled_error_handler

setup_logging(settings.log_level)

app = FastAPI()
app.add_exception_handler(OpsError, ops_error_handler)
app.add_exception_handler(Exception, unhandled_error_handler)


@app.middleware("http")
async def request_context(request: Request, call_next):
    """请求级日志字段（PRD §29）：request_id 透传响应头，站点随路径。"""
    rid = new_request_id()
    path_parts = request.url.path.split("/")
    site_id = path_parts[3] if len(path_parts) > 3 and path_parts[1] == "api" and path_parts[2] == "sites" else "-"
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
