from fastapi import Request
from fastapi.responses import JSONResponse


class OpsError(Exception):
    """外部资源操作失败的业务异常，渲染为统一错误包络（PRD §28）。"""

    def __init__(self, error_code: str, message: str, resource: str | None = None):
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.resource = resource


def _body(error_code: str, message: str, resource: str | None) -> dict:
    return {
        "success": False,
        "error_code": error_code,
        "message": message,
        "resource": resource,
    }


async def ops_error_handler(request: Request, exc: OpsError) -> JSONResponse:
    return JSONResponse(
        status_code=502, content=_body(exc.error_code, exc.message, exc.resource)
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500, content=_body("INTERNAL_ERROR", "Internal server error", None)
    )
