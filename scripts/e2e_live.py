"""E2E 主路径（PRD §32）：对真实环境按顺序走完 V1 核心用户路径。

用法：uv run --env-file .env python scripts/e2e_live.py
覆盖：建站 → 配 4 类资源 → 连接测试 → Server 指标+诊断 → Redis SCAN/编辑/
倒计时删除（后端等价物）→ MQ → Robot → Overview → 操作日志 → 导出导入 → 清理。
任何一步失败都保证清理站点，不留脏数据。
"""

import asyncio
import sys

import httpx

BASE = "http://127.0.0.1:8123"
SITE = "e2e-check"

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    mark = "PASS" if cond else "FAIL"
    if cond:
        PASS += 1
    else:
        FAIL += 1
    print(f"[{mark}] {name} {detail if not cond else ''}")


async def main() -> int:
    import os
    from urllib.parse import urlparse

    platform = urlparse(os.environ["OPS_REDIS_URL"])
    redis_host = platform.hostname
    redis_port = platform.port or 6379

    async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
        # 0. 幂等清理（上次运行可能残留）
        await c.delete(f"/api/sites/{SITE}")

        try:
            await run_checks(c, redis_host, redis_port)
        finally:
            # 任何一步失败也保证清理，不留脏数据
            r = await c.delete(f"/api/sites/{SITE}")
            check("cleanup", r.status_code == 204)

    print(f"\n==== E2E: {PASS} passed, {FAIL} failed ====")
    return 1 if FAIL else 0


async def run_checks(c: httpx.AsyncClient, redis_host: str, redis_port: int) -> None:
    import os

    # 1. 建站 + 四类资源
    r = await c.post("/api/sites", json={"id": SITE, "name": "E2E"})
    check("create site", r.status_code == 201)

    ssh = {"id": "s1", "name": "srv", "host": os.environ["SERVER_IP"], "port": 22,
           "username": os.environ["SERVER_SSH_USER_NAME"], "password": os.environ["SERVER_SSH_PASSWORD"]}
    redis_cfg = {"id": "r1", "name": "redis", "host": redis_host, "port": redis_port}
    mq_cfg = {"id": "m1", "name": "amq", "host": os.environ["ARTEMIS_URI"], "port": 8161,
              "username": os.environ["ARTEMIS_USER_NAME"], "password": os.environ["ARTEMIS_PASSOWRD"]}
    robot_cfg = {"id": "b1", "name": "env50", "base_url": "http://10.102.129.50:19030",
                 "list_path": "/mission/robot/info/active"}
    for path, body in [("servers", ssh), ("redis", redis_cfg), ("mq", mq_cfg), ("robot-instances", robot_cfg)]:
        r = await c.post(f"/api/sites/{SITE}/{path}", json=body)
        check(f"create {path}", r.status_code == 201)

    # 2. 密码不回显
    r = await c.get(f"/api/sites/{SITE}/servers")
    check("password not echoed", r.json()[0]["password"] == "")

    # 3. 连接测试（四类）
    for ttype, cfg in [("server", ssh), ("redis", redis_cfg), ("mq", mq_cfg), ("robot", robot_cfg)]:
        r = await c.post("/api/test-connection", json={"type": ttype, "config": cfg})
        check(f"test {ttype}", r.status_code == 200 and r.json()["success"], r.text[:120])

    # 4. Server 指标 + 诊断（环境 SSH 不通时报告失败而非崩溃）
    r = await c.get(f"/api/sites/{SITE}/servers/s1/metrics")
    body = r.json()
    ok = r.status_code == 200 and body.get("cpu", {}).get("cores") and "diagnosis" in body
    check("server metrics", ok, f"env SSH 凭据需有效（SERVER_IP={ssh['host']}）" if not ok else "")
    if ok:
        check("server diagnosis shape", body["diagnosis"]["status"] in ("HEALTHY", "WARNING", "CRITICAL"))
        r = await c.get(f"/api/sites/{SITE}/servers/s1/processes")
        check("server processes", r.status_code == 200 and isinstance(r.json(), list) and r.json())

    # 5. Redis SCAN + 编辑 + 删除（倒计时的后端等价物是受控 operations）
    await _seed_redis_keys(redis_host, redis_port)
    r = await c.get(f"/api/sites/{SITE}/redis/r1/keys", params={"db": 6, "pattern": "e2e:*"})
    keys = {k["key"] for k in r.json()["keys"]}
    check("redis SCAN", r.status_code == 200 and {"e2e:a", "e2e:h"} <= keys)
    r = await c.post(f"/api/sites/{SITE}/redis/r1/operations",
                     json={"op": "set", "db": 6, "key": "e2e:a", "type": "string", "value": "edited"})
    check("redis edit", r.status_code == 200)
    r = await c.get(f"/api/sites/{SITE}/redis/r1/key", params={"db": 6, "key": "e2e:a"})
    check("redis re-read", r.json()["value"] == "edited")
    r = await c.post(f"/api/sites/{SITE}/redis/r1/operations", json={"op": "delete", "db": 6, "key": "e2e:a"})
    check("redis delete", r.status_code == 200)
    r = await c.post(f"/api/sites/{SITE}/redis/r1/operations", json={"op": "flushall"})
    check("dangerous op rejected", r.status_code == 422)

    # 6. MQ + Robot
    r = await c.get(f"/api/sites/{SITE}/mq/m1/overview")
    check("mq overview", r.status_code == 200 and r.json().get("version"), r.text[:120])
    r = await c.get(f"/api/sites/{SITE}/mq/m1/queues")
    check("mq queues", r.status_code == 200 and any(q.get("diagnosis") for q in r.json()))
    r = await c.get(f"/api/sites/{SITE}/robots")
    check("robot list", r.status_code == 200 and len(r.json()) > 0, f"got {len(r.json()) if r.status_code == 200 else '-'}")

    # 7. Overview + 操作日志
    r = await c.get(f"/api/sites/{SITE}/overview")
    body = r.json()
    check("overview", r.status_code == 200 and body["overall"] in ("HEALTHY", "WARNING", "CRITICAL"))
    check("overview recent ops", len(body["recent_ops"]) > 0)
    r = await c.get("/api/audit", params={"page": 1, "size": 20})
    body = r.json()
    check("audit page", r.status_code == 200 and body["total"] > 0
          and any(e["operation"] == "REDIS_DELETE_KEY" for e in body["items"]))

    # 8. 导出 → 清 → 导入 roundtrip
    r = await c.post("/api/sites/export")
    exported = r.json()
    r = await c.delete(f"/api/sites/{SITE}")
    check("delete site", r.status_code == 204)
    r = await c.post("/api/sites/import", json=exported)
    check("import", r.status_code == 200 and r.json()["imported"] >= 1)
    r = await c.get(f"/api/sites/{SITE}/redis")
    check("roundtrip resource", r.status_code == 200 and r.json()[0]["id"] == "r1")


async def _seed_redis_keys(redis_host: str, redis_port: int) -> None:
    import redis.asyncio as aioredis

    c = aioredis.from_url(f"redis://{redis_host}:{redis_port}/6", decode_responses=True)
    await c.set("e2e:a", "orig")
    await c.hset("e2e:h", mapping={"f": "1"})
    await c.aclose()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
