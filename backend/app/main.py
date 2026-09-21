from fastapi import FastAPI

from backend.app.core.redis import get_platform_redis
from backend.app.modules import register_all
from backend.app.shared.errors import OpsError, ops_error_handler, unhandled_error_handler

app = FastAPI()
app.add_exception_handler(OpsError, ops_error_handler)
app.add_exception_handler(Exception, unhandled_error_handler)
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
