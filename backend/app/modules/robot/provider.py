"""Robot HTTP Provider（PRD §12）：业务层不直接依赖具体 Robot API。

V1 约定：GET {base_url}/robots 列表、GET {base_url}/robots/{id} 详情，
返回 JSON。字段映射尽量宽容（多种常见命名），现场 API 结构确认后只需调整
映射层（normalize_robot），业务与 API 层不动。
"""

from typing import Any

import httpx

from backend.app.core.config import settings
from backend.app.shared.errors import OpsError
from backend.app.shared.timeout import with_timeout

# 常见字段名候选（按优先级）
_FIELD_CANDIDATES: dict[str, tuple[str, ...]] = {
    "id": ("id", "robotId", "robot_id", "robotID"),
    "name": ("name", "robotName", "robot_name"),
    "status": ("status", "state", "runStatus", "run_status"),
    "battery": ("battery", "batteryLevel", "battery_level", "power"),
    "station": ("station", "currentStation", "current_station", "position", "location"),
    "task": ("task", "currentTask", "current_task", "taskName"),
    "error": ("error", "errorMsg", "error_message", "fault"),
    "last_update": ("lastUpdate", "last_update", "updateTime", "timestamp"),
}


def _pick(raw: dict[str, Any], field: str) -> Any:
    for key in _FIELD_CANDIDATES[field]:
        if key in raw and raw[key] is not None:
            return raw[key]
    return None


def normalize_robot(raw: dict[str, Any]) -> dict[str, Any]:
    """原始 API 字典 -> PRD §12.1 统一结构（纯函数）。"""
    return {field: _pick(raw, field) for field in _FIELD_CANDIDATES}


class RobotProvider:
    """统一接口（PRD §12）：未来其他厂商 API 换实现即可。"""

    async def get_robot_list(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def get_robot_detail(self, robot_id: str) -> dict[str, Any]:
        raise NotImplementedError

    async def run_test(self) -> str:
        raise NotImplementedError


class HttpRobotProvider(RobotProvider):
    def __init__(self, config: dict[str, Any]):
        self._base_url: str = str(config.get("base_url") or "").rstrip("/")
        if not self._base_url:
            raise OpsError("INVALID_OPERATION", "robot base_url required", status_code=400)
        self._username: str = config.get("username") or ""
        self._password: str = config.get("password") or ""

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            auth=(self._username, self._password) if self._username else None,
            timeout=httpx.Timeout(settings.http_read_timeout, connect=settings.http_connect_timeout),
        )

    async def _get(self, c: httpx.AsyncClient, path: str) -> Any:
        try:
            resp = await with_timeout(
                c.get(path), settings.http_read_timeout, resource=self._base_url
            )
        except OpsError:
            raise
        except httpx.HTTPError as e:
            raise OpsError("REMOTE_CONNECTION_FAILED", f"Robot API request failed: {e}", self._base_url) from None
        if resp.status_code in (401, 403):
            raise OpsError("AUTH_FAILED", "Robot API authentication failed", self._base_url, status_code=502)
        if resp.status_code >= 400:
            raise OpsError("REMOTE_BAD_RESPONSE", f"Robot API HTTP {resp.status_code}", self._base_url)
        try:
            return resp.json()
        except ValueError:
            raise OpsError("REMOTE_BAD_RESPONSE", "Robot API returned non-JSON", self._base_url) from None

    @staticmethod
    def _unwrap_list(data: Any) -> list[dict[str, Any]]:
        """宽容解包：支持直接数组或 {data: [...]} / {robots: [...]} 信封。"""
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if isinstance(data, dict):
            for key in ("data", "robots", "list", "result"):
                inner = data.get(key)
                if isinstance(inner, list):
                    return [x for x in inner if isinstance(x, dict)]
        return []

    async def get_robot_list(self) -> list[dict[str, Any]]:
        async with self._client() as c:
            data = await self._get(c, "/robots")
        return [normalize_robot(x) for x in self._unwrap_list(data)]

    async def get_robot_detail(self, robot_id: str) -> dict[str, Any]:
        async with self._client() as c:
            data = await self._get(c, f"/robots/{robot_id}")
        raw = data if isinstance(data, dict) and not self._is_envelope(data) else self._unwrap_list(data) or [{}]
        if isinstance(raw, list):
            raw = raw[0] if raw else {}
        if not raw:
            raise OpsError("REMOTE_BAD_RESPONSE", f"robot not found: {robot_id}", self._base_url)
        return normalize_robot(raw)

    @staticmethod
    def _is_envelope(data: dict) -> bool:
        return not any(k in data for k in ("id", "robotId", "robot_id"))

    async def run_test(self) -> str:
        async with self._client() as c:
            data = await self._get(c, "/robots")
        return f"Robot API OK, {len(self._unwrap_list(data))} robots"
