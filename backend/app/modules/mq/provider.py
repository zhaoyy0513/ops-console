"""ActiveMQ Artemis Provider（PRD §9）：经 Jolokia 读 Management 数据。

httpx + Basic Auth；broker 名未知时用 broker=* 通配（现场探测可用）。
解析函数均为纯函数，用现场抓取的 Jolokia 响应样本做单测。
"""

import json
from typing import Any

import httpx

from backend.app.core.config import settings
from backend.app.shared.errors import OpsError
from backend.app.shared.timeout import with_timeout

BROKER_MBEAN = "org.apache.activemq.artemis:broker=*"
QUEUES_MBEAN = "org.apache.activemq.artemis:component=addresses,broker=*,subcomponent=queues,*"
# 限属性读取：全属性 49 个 2.1s，限 8 个 0.4s（现场 104 队列实测），3s 轮询下不再超时
QUEUE_ATTRS = "Name,Address,RoutingType,MessageCount,ConsumerCount,DeliveringCount,MessagesAdded,MessagesAcknowledged"
ADDRESSES_MBEAN = "org.apache.activemq.artemis:component=addresses,broker=*,queue=*,*"
MEMORY_MBEAN = "java.lang:type=Memory"
THREADING_MBEAN = "java.lang:type=Threading"
GC_MBEAN = "java.lang:type=GarbageCollector,name=*"


class ArtemisProvider:
    def __init__(self, config: dict[str, Any]):
        self._host: str = config["host"]
        self._port: int = int(config.get("port") or 8161)
        self._username: str = config.get("username") or ""
        self._password: str = config.get("password") or ""
        self._path: str = config.get("jolokia_path") or "/console/jolokia"

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=f"http://{self._host}:{self._port}{self._path}",
            auth=(self._username, self._password) if self._username else None,
            timeout=httpx.Timeout(settings.mq_api_timeout, connect=settings.http_connect_timeout),
        )

    async def _read(self, c: httpx.AsyncClient, mbean: str) -> Any:
        try:
            resp = await with_timeout(
                c.get(f"/read/{mbean}"), settings.mq_api_timeout, resource=self._host
            )
        except OpsError:
            raise
        except httpx.HTTPError as e:
            raise OpsError("REMOTE_CONNECTION_FAILED", f"Jolokia request failed: {e}", self._host) from None
        if resp.status_code == 401:
            raise OpsError("AUTH_FAILED", "Jolokia authentication failed", self._host, status_code=502)
        try:
            body = resp.json()
        except ValueError:
            raise OpsError("REMOTE_BAD_RESPONSE", "Jolokia returned non-JSON", self._host) from None
        if body.get("status") != 200:
            raise OpsError(
                "REMOTE_BAD_RESPONSE",
                f"Jolokia error {body.get('status')}: {str(body.get('error'))[:200]}",
                self._host,
            )
        return body.get("value")

    async def _read_wildcard(self, c: httpx.AsyncClient, mbean: str) -> dict[str, dict]:
        """wildcard read 统一返回 {objectName: attrs}；单 bean 时 Jolokia 直接给 attrs。"""
        value = await self._read(c, mbean)
        if value and "mbean" not in value and all(isinstance(v, dict) for v in value.values()):
            return value
        return {"single": value or {}}

    async def exec_operation(self, mbean: str, operation: str, args: list | None = None) -> Any:
        """Jolokia exec（管理操作，当前仅限清空积压队列等白名单调用）。"""
        payload = {"type": "exec", "mbean": mbean, "operation": operation,
                   "arguments": args or []}
        async with self._client() as c:
            try:
                resp = await with_timeout(
                    c.post("", json=payload), settings.mq_api_timeout, resource=self._host
                )
            except httpx.HTTPError as e:
                raise OpsError("REMOTE_CONNECTION_FAILED", f"Jolokia request failed: {e}", self._host) from None
            if resp.status_code == 401:
                raise OpsError("AUTH_FAILED", "Jolokia authentication failed", self._host, status_code=502)
            try:
                body = resp.json()
            except ValueError:
                raise OpsError("REMOTE_BAD_RESPONSE", "Jolokia returned non-JSON", self._host) from None
            if body.get("status") != 200:
                raise OpsError(
                    "REMOTE_BAD_RESPONSE",
                    f"Jolokia error {body.get('status')}: {str(body.get('error'))[:200]}",
                    self._host,
                )
            return body.get("value")

    async def empty_queue(self, mbean: str) -> Any:
        """清空队列积压消息。mbean 已精确到单队列（address+queue+routing-type），
        removeAllMessages() 只作用于该队列。不用 removeMessages(null)：Jolokia 把
        None 序列化为 JSON null，Artemis 解析 null filter 抛 IllegalArgumentException
        （线上实测）。此探测确认该 broker 无 emptyQueue 操作。"""
        return await self.exec_operation(mbean, "removeAllMessages")

    async def browse_queue(self, mbean: str, limit: int = 20) -> list[dict[str, Any]]:
        """浏览队列消息（Artemis 2.19 用 listMessages(filter)——没有 browse/getMessage）。

        2.19 管理接口不提供消息正文（body），只能返回元数据 + 业务自定义
        属性（过滤 _AMQ_/__HDR_ 内部键）；升级 2.21+ 后可扩展 body 展示。
        """
        value = await self.exec_operation(mbean, "listMessages", [""])
        messages: list[dict[str, Any]] = []
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                raise OpsError("REMOTE_BAD_RESPONSE", "listMessages 返回非 JSON", self._host) from None
        if isinstance(value, dict):  # 某些版本包在 {data: [...]} 信封
            for key in ("data", "messages", "result"):
                if isinstance(value.get(key), list):
                    value = value[key]
                    break
        if isinstance(value, list):
            for m in value[:limit]:
                if not isinstance(m, dict):
                    continue
                properties = {
                    k: (v if isinstance(v, (str, int, float, bool)) else str(v))
                    for k, v in m.items()
                    if not k.startswith(("_AMQ_", "__AMQ_", "__HDR_"))
                    and k not in ("messageID", "timestamp", "priority", "durable")
                }
                body = m.get("body")
                if body is None:
                    body = m.get("text")
                messages.append({
                    "message_id": m.get("messageID"),
                    "priority": m.get("priority"),
                    "timestamp": m.get("timestamp"),
                    "durable": m.get("durable"),
                    "properties": properties,
                    # 2.19 无正文；2.21+ 若返回 body/text 自动透传，前端预留展示位
                    "body": body if isinstance(body, str) else (str(body) if body is not None else None),
                })
        return messages

    # ---------- 数据获取 ----------

    async def get_overview(self) -> dict[str, Any]:
        async with self._client() as c:
            brokers = await self._read_wildcard(c, BROKER_MBEAN)
            memory = await self._read(c, MEMORY_MBEAN)
            threading = await self._read(c, THREADING_MBEAN)
            gc = await self._read_wildcard(c, GC_MBEAN)
        broker = next(iter(brokers.values()), {})
        return {
            **normalize_broker(broker),
            "jvm": normalize_jvm(memory, threading, gc),
        }

    async def get_queues(self) -> list[dict[str, Any]]:
        async with self._client() as c:
            value = await self._read_wildcard(c, f"{QUEUES_MBEAN}/{QUEUE_ATTRS}")
            try:
                # 单独读 FirstMessageAge：老版本没有该属性时 Jolokia 会整批报错，
                # 隔离成独立请求，失败只让这一列显示 '-'，不影响其它字段
                ages = await self._read(c, f"{QUEUES_MBEAN}/FirstMessageAge")
            except OpsError:
                ages = {}
        return normalize_queues(value, ages if isinstance(ages, dict) else {})

    async def get_addresses(self) -> list[dict[str, Any]]:
        async with self._client() as c:
            value = await self._read_wildcard(c, ADDRESSES_MBEAN)
        return normalize_addresses(value)

    async def run_test(self) -> str:
        async with self._client() as c:
            brokers = await self._read_wildcard(c, BROKER_MBEAN)
        broker = next(iter(brokers.values()), {})
        version = broker.get("Version") or "?"
        return f"Jolokia OK, Artemis {version}"


# ---------- 纯函数解析（样本单测） ----------


def normalize_broker(attrs: dict[str, Any]) -> dict[str, Any]:
    status_raw = attrs.get("Status")
    state = None
    if isinstance(status_raw, str):
        try:
            state = json.loads(status_raw).get("server", {}).get("state")
        except ValueError:
            state = status_raw
    elif isinstance(status_raw, dict):
        state = status_raw.get("server", {}).get("state")
    # Artemis 2.19 无 Status 属性：能经 Jolokia 读到 broker 属性本身即在线
    if not state:
        state = "STARTED"

    def _int(v):
        return int(v) if isinstance(v, (int, float)) else None

    return {
        "name": attrs.get("Name"),
        "status": state,
        "version": attrs.get("Version"),
        "uptime": attrs.get("Uptime"),
        "connections": _int(attrs.get("ConnectionCount")),
        "total_connections": _int(attrs.get("TotalConnectionCount")),
        "sessions": _int(attrs.get("SessionCount")),
        "consumers": _int(attrs.get("TotalConsumerCount")),
        "producers": _int(attrs.get("TotalProducerCount")),
        "addresses": _int(attrs.get("AddressCount")),
        "address_memory_usage": _int(attrs.get("AddressMemoryUsage")),
        "global_max_size": _int(attrs.get("GlobalMaxSize")),
    }


def normalize_jvm(memory: dict, threading: dict, gc: dict) -> dict[str, Any]:
    heap = memory.get("HeapMemoryUsage") or {}
    nonheap = memory.get("NonHeapMemoryUsage") or {}
    collectors = []
    for objname, attrs in (gc or {}).items():
        # 兼容两种 ObjectName：name="G1 Old"（带引号）与 name=G1 Old,type=...（无引号，2.19 实测）
        if 'name="' in objname:
            name = objname.split('name="', 1)[1].split('"', 1)[0]
        elif "name=" in objname:
            after = objname.split("name=", 1)[1]
            name = after.split(",", 1)[0]
        else:
            name = objname
        collectors.append({
            "name": name,
            "count": attrs.get("CollectionCount"),
            "time_ms": attrs.get("CollectionTime"),
        })
    return {
        "heap_used": heap.get("used"),
        "heap_max": heap.get("max"),
        "non_heap_used": nonheap.get("used"),
        "threads": threading.get("ThreadCount"),
        "gc": collectors,
    }


def parse_first_message_age(value: Any) -> int | None:
    """FirstMessageAge（毫秒）：缺失/负数/非数字 → None（空队列 Artemis 可能给 -1）。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value) if value >= 0 else None


def normalize_queues(value: dict[str, dict], ages: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    ages = ages or {}
    queues = []
    for objname, attrs in value.items():
        if "subcomponent=queues" not in objname:
            continue  # 通配可能带出 address 本体
        age_attrs = ages.get(objname)
        queues.append({
            "name": attrs.get("Name"),
            "address": attrs.get("Address"),
            "routing_type": attrs.get("RoutingType"),
            "message_count": attrs.get("MessageCount"),
            "consumer_count": attrs.get("ConsumerCount"),
            "delivering_count": attrs.get("DeliveringCount"),
            "messages_added": attrs.get("MessagesAdded"),
            "messages_acknowledged": attrs.get("MessagesAcknowledged"),
            # 最老一条消息已滞留时长；读取失败/属性不存在 → None（不影响其它字段）
            "first_message_age_ms": parse_first_message_age(
                age_attrs.get("FirstMessageAge") if isinstance(age_attrs, dict) else None),
            # 完整 ObjectName：清空积压等管理操作需要精确定位（不经前端回传）
            "_mbean": objname,
        })
    queues.sort(key=lambda q: (q["message_count"] or 0) if isinstance(q["message_count"], (int, float)) else 0,
                reverse=True)
    return queues


def normalize_addresses(value: dict[str, dict]) -> list[dict[str, Any]]:
    addresses = []
    for objname, attrs in value.items():
        if "component=addresses" not in objname:
            continue
        addresses.append({
            "name": attrs.get("Name") or attrs.get("address"),
            "message_count": attrs.get("MessageCount"),
            "consumer_count": attrs.get("ConsumerCount"),
            "producer_count": attrs.get("ProducerCount"),
            "address_size": attrs.get("AddressSize"),
        })
    addresses.sort(key=lambda a: (a["message_count"] or 0) if isinstance(a["message_count"], (int, float)) else 0,
                   reverse=True)
    return addresses
