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

# 常见字段名候选（按优先级）；现场同厂商产品线字段基本一致，
# 新增环境只需在此扩充候选/转换，不改业务与 API 层
_FIELD_CANDIDATES: dict[str, tuple[str, ...]] = {
    "id": ("robotCode", "id", "robotId", "robot_id", "robotID"),
    "name": ("robotName", "name", "robot_name"),
    "status": ("online", "status", "state", "runStatus", "run_status"),
    "battery": ("battery", "batteryLevel", "battery_level", "power"),
    "station": ("station", "currentStation", "current_station", "position", "location"),
    "task": ("task", "currentTask", "current_task", "taskName"),
    "error": ("errorCode", "error", "errorMsg", "error_message", "fault"),
    "last_update": ("lastUpdate", "last_update", "updateTime", "timestamp"),
    "x": ("x",),
    "y": ("y",),
}

_EPOCH_MS_KEYS = ("lastUpdate", "last_update", "updateTime", "createDate")


def _pick(raw: dict[str, Any], field: str) -> Any:
    for key in _FIELD_CANDIDATES[field]:
        if key in raw and raw[key] is not None:
            return raw[key]
    return None


def _online_to_status(raw: dict[str, Any]) -> Any:
    """online 字段优先转语义（现场环境 12：online:1 在线 / 0 离线）；
    无 online 时返回原始 status 值（数字枚举语义待现场确认，不猜）。"""
    online = raw.get("online")
    if online is not None:
        return "online" if online in (1, True, "1") else "offline"
    return _pick(raw, "status")


def _station_from_xy(raw: dict[str, Any]) -> Any:
    named = _pick(raw, "station")
    if named is not None:
        return named
    x, y = raw.get("x"), raw.get("y")
    if x is not None and y is not None:
        return f"({x},{y})"  # 无命名站点时退化为坐标（现场 50/12 均如此）
    return None


def _last_update(raw: dict[str, Any]) -> Any:
    for key in _EPOCH_MS_KEYS:
        v = raw.get(key)
        if isinstance(v, (int, float)) and v > 10**12:  # epoch ms
            from datetime import datetime, timezone

            return datetime.fromtimestamp(v / 1000, tz=timezone.utc).isoformat(timespec="seconds")
        if v is not None:
            return v
    return None


def normalize_robot(
    raw: dict[str, Any],
    field_map: dict[str, str] | None = None,
    value_map: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    """原始 API 字典 -> PRD §12.1 统一结构（纯函数）。

    field_map（实例级配置）的值支持两种形态：
    1. 字段名绑定："battery": "power" -> 取 raw["power"]
    2. 模板拼接："station": "({x},{y})" -> 求值占位符得 "(33,37)"
       含 {xxx} 占位符的值按模板处理，{xxx} 替换为 raw 中的对应值
    未配置的字段走内置候选。

    value_map（实例级配置）为值->展示映射：{"status": {"1": "CREATE"}}，
    作用于字段取值/模板求值之后，字符串化匹配，未命中保留原值。
    """
    import re

    def eval_value(upstream: str) -> Any:
        if re.search(r"\{\w+\}", upstream):
            return re.sub(r"\{(\w+)\}", lambda m: str(raw.get(m.group(1), "")), upstream)
        return raw.get(upstream)

    def mapped(field: str) -> Any:
        if field_map:
            upstream = field_map.get(field)
            if upstream:
                v = eval_value(upstream)
                if v is not None and v != "":
                    return v
        return None

    def pick(field: str) -> Any:
        m = mapped(field)
        if m is not None:
            return m
        for key in _FIELD_CANDIDATES[field]:
            if key in raw and raw[key] is not None:
                return raw[key]
        return None

    def online_to_status() -> Any:
        online = raw.get("online")
        if online is not None:
            return "online" if online in (1, True, "1") else "offline"
        s = mapped("status")
        return s if s is not None else _pick(raw, "status")

    def station() -> Any:
        named = pick("station")
        if named is not None:
            return named
        x, y = raw.get("x"), raw.get("y")
        if x is not None and y is not None:
            return f"({x},{y})"
        return None

    def last_update() -> Any:
        m = mapped("last_update")
        if m is not None:
            return m
        for key in _EPOCH_MS_KEYS:
            v = raw.get(key)
            if isinstance(v, (int, float)) and v > 10**12:  # epoch ms
                from datetime import datetime, timezone

                return datetime.fromtimestamp(v / 1000, tz=timezone.utc).isoformat(timespec="seconds")
            if v is not None:
                return v
        return None

    def apply_value_map(v: Any, field: str) -> Any:
        """值->展示映射（枚举翻译）：字符串化匹配（数字 1 与 "1" 互通），
        未命中返回原值。作用于字段映射求值之后的最终值。"""
        vm = value_map.get(field) if value_map else None
        if vm and v is not None:
            return vm.get(str(v), v)
        return v

    return {
        "id": apply_value_map(pick("id"), "id"),
        "name": apply_value_map(pick("name"), "name"),
        "status": apply_value_map(online_to_status(), "status"),
        "battery": apply_value_map(pick("battery"), "battery"),
        "station": apply_value_map(station(), "station"),
        "lift": apply_value_map(raw.get("lift"), "lift"),
        "shelf_code": apply_value_map(
            raw.get("shelfCode") or raw.get("shelf_code"), "shelf_code"),
        "task": apply_value_map(pick("task"), "task"),
        "error": apply_value_map(pick("error"), "error"),
        "last_update": last_update(),
        "x": raw.get("x"),
        "y": raw.get("y"),
    }


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
        # 现场仅一个 URL 字段：base_url 即完整地址；地址与路径分离时才配 list_path
        self._list_path: str = str(config.get("list_path") or "")
        self._username: str = config.get("username") or ""
        self._password: str = config.get("password") or ""
        # 实例级字段映射（业务字段 -> 上游字段名），应对不同环境的响应结构差异
        self._field_map: dict[str, str] | None = config.get("field_map") or None
        self._value_map: dict[str, dict[str, str]] | None = config.get("value_map") or None

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
        """宽容解包：直接数组 / 常见信封 key / 自动探测 list-of-dict 信封
        （现场信封 key 不统一：records / result / data ...）。"""
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if isinstance(data, dict):
            for key in ("data", "records", "result", "robots", "list"):
                inner = data.get(key)
                if isinstance(inner, list):
                    return [x for x in inner if isinstance(x, dict)]
            # 自动探测：任意值中第一个非空 list-of-dict
            for inner in data.values():
                if isinstance(inner, list) and inner and isinstance(inner[0], dict):
                    return [x for x in inner if isinstance(x, dict)]
        return []

    def _list_request_path(self) -> str:
        # list_path 为空时请求 base_url 本身（绝对 URL，绕过 httpx 的 base_url
        # 路径合并——实测它会给 ".../list" 补尾斜杠，Spring 端 404/500）
        return self._list_path or self._base_url

    async def get_robot_list(self) -> list[dict[str, Any]]:
        async with self._client() as c:
            data = await self._get(c, self._list_request_path())
        return [normalize_robot(x, self._field_map, self._value_map) for x in self._unwrap_list(data)]

    async def get_raw_sample(self) -> dict[str, Any] | None:
        """取第一条原始 JSON 数据（字段映射配置用，未经 normalize）。"""
        async with self._client() as c:
            data = await self._get(c, self._list_request_path())
        raw = self._unwrap_list(data)
        return raw[0] if raw else None

    async def get_robot_detail(self, robot_id: str) -> dict[str, Any]:
        # 列表已含全部展示字段（现场两个环境均如此）：详情 = 列表内查找，
        # 免去第二个端点的格式假设
        for robot in await self.get_robot_list():
            if str(robot.get("id")) == str(robot_id):
                return robot
        raise OpsError("REMOTE_BAD_RESPONSE", f"robot not found: {robot_id}", self._base_url)

    async def run_test(self) -> str:
        async with self._client() as c:
            data = await self._get(c, self._list_request_path())
        return f"Robot API OK, {len(self._unwrap_list(data))} robots"
