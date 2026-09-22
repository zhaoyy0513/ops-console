"""SSH 只读诊断 Provider（PRD §8/§10）。

后端内部实现细节：固定白名单命令、按需连接查完即关（Decision 004）。
本模块对外只暴露结构化数据——前端不感知命令，也无法传入任何命令。
"""

import re
from typing import Any

import asyncssh

from backend.app.core.config import settings
from backend.app.shared.errors import OpsError
from backend.app.shared.timeout import with_timeout

# 只读诊断命令白名单：模块常量，非用户输入。LC_ALL=C 保证输出格式可解析。
COMMANDS: dict[str, str] = {
    "cpu": "LC_ALL=C top -bn1 | head -6",
    "load": "LC_ALL=C uptime",
    "cores": "nproc",
    "memory": "LC_ALL=C free -m",
    "disk_usage": "LC_ALL=C df -hP",
    "disk_inode": "LC_ALL=C df -iP",
    "network": "cat /proc/net/dev",
    "processes": "LC_ALL=C ps aux --sort=-%cpu | head -11",
}


# ---------- 解析器（纯函数；字段缺失返回 None，不让单条解析拖垮整体） ----------


def parse_cpu(text: str) -> dict[str, float | None]:
    """top 输出 -> {usage, iowait}，usage = 100 - idle。"""
    idle = re.search(r"(\d+\.?\d*)\s*id[, ]", text)
    wa = re.search(r"(\d+\.?\d*)\s*wa[, ]", text)
    return {
        "usage": round(100 - float(idle.group(1)), 1) if idle else None,
        "iowait": float(wa.group(1)) if wa else None,
    }


def parse_load(text: str) -> dict[str, float | None]:
    """uptime 输出 -> {load1, load5, load15}。"""
    m = re.search(r"load average:\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)", text)
    if not m:
        return {"load1": None, "load5": None, "load15": None}
    return {"load1": float(m.group(1)), "load5": float(m.group(2)), "load15": float(m.group(3))}


def parse_memory(text: str) -> dict[str, int | None]:
    """free -m 输出 -> MB 计的内存/交换分区字段。"""
    mem = re.search(r"^Mem:\s+(\d+)\s+(\d+)\s+\d+\s+\d+\s+(\d+)\s+(\d+)", text, re.M)
    swap = re.search(r"^Swap:\s+(\d+)\s+(\d+)", text, re.M)
    result: dict[str, int | None] = {
        "total": None,
        "used": None,
        "available": None,
        "cached": None,
        "swap_total": None,
        "swap_used": None,
    }
    if mem:
        result.update(
            total=int(mem.group(1)),
            used=int(mem.group(2)),
            cached=int(mem.group(3)),
            available=int(mem.group(4)),
        )
    if swap:
        result.update(swap_total=int(swap.group(1)), swap_used=int(swap.group(2)))
    return result


def parse_df(text: str) -> list[dict[str, Any]]:
    """df -hP / df -iP 共用解析 -> [{mount, size, used, avail, use_percent}]。"""
    rows: list[dict[str, Any]] = []
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 6:
            continue
        try:
            percent = int(parts[4].rstrip("%"))
        except ValueError:
            continue
        rows.append(
            {
                "filesystem": parts[0],
                "size": parts[1],
                "used": parts[2],
                "avail": parts[3],
                "use_percent": percent,
                "mount": parts[5],
            }
        )
    return rows


def merge_disk(usage_rows: list[dict], inode_rows: list[dict]) -> list[dict[str, Any]]:
    """按挂载点合并容量与 inode 两份 df 结果。"""
    by_mount = {r["mount"]: dict(r) for r in usage_rows}
    for r in inode_rows:
        row = by_mount.setdefault(r["mount"], dict(r))
        row["inode_percent"] = r["use_percent"]
    return list(by_mount.values())


def parse_network(text: str) -> dict[str, int]:
    """/proc/net/dev -> 非 lo 接口聚合 {rx, tx, errors, dropped}（bytes）。"""
    rx = tx = errors = dropped = 0
    for line in text.splitlines():
        if ":" not in line:
            continue
        iface, _, data = line.partition(":")
        if iface.strip() == "lo":
            continue
        cols = data.split()
        if len(cols) < 12:
            continue
        try:
            rx += int(cols[0])
            tx += int(cols[8])
            errors += int(cols[2]) + int(cols[10])
            dropped += int(cols[3]) + int(cols[11])
        except ValueError:
            continue
    return {"rx": rx, "tx": tx, "errors": errors, "dropped": dropped}


def parse_processes(text: str) -> list[dict[str, Any]]:
    """ps aux（按 %cpu 排序）-> [{pid, command, cpu_percent, mem_percent}]。"""
    rows: list[dict[str, Any]] = []
    for line in text.splitlines()[1:]:
        parts = line.split(None, 10)
        if len(parts) < 11:
            continue
        try:
            rows.append(
                {
                    "pid": int(parts[1]),
                    "cpu_percent": float(parts[2]),
                    "mem_percent": float(parts[3]),
                    "command": parts[10],
                }
            )
        except ValueError:
            continue
    return rows


# ---------- Provider（PRD §8.5 抽象 + SSH 实现） ----------


class ServerMetricsProvider:
    """业务层只依赖此接口；未来 Prometheus 实现不改动 API/业务层。"""

    async def get_metrics(self) -> dict[str, Any]:
        raise NotImplementedError

    async def get_processes(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def get_disk(self) -> list[dict[str, Any]]:
        raise NotImplementedError


class SSHServerMetricsProvider(ServerMetricsProvider):
    def __init__(self, config: dict[str, Any]):
        self._host: str = config["host"]
        self._port: int = int(config.get("port") or 22)
        self._username: str = config.get("username") or ""
        self._password: str = config.get("password") or ""
        self._private_key: str = config.get("private_key") or ""

    async def _connect(self):
        # ponytail: known_hosts=None 跳过主机钥匙校验，内部工具可接受；
        # 有现场安全要求时改为提供 known_hosts 文件
        kwargs: dict[str, Any] = {
            "host": self._host,
            "port": self._port,
            "known_hosts": None,
            "connect_timeout": settings.ssh_connect_timeout,
        }
        if self._username:
            kwargs["username"] = self._username
        if self._private_key:
            kwargs["client_keys"] = [self._private_key]
        else:
            kwargs["password"] = self._password
        try:
            return await asyncssh.connect(**kwargs)
        except (asyncssh.Error, OSError) as e:
            raise OpsError(
                "REMOTE_CONNECTION_FAILED", f"SSH connect failed: {e}", self._host
            ) from None

    async def _collect(self, names: list[str]) -> dict[str, str]:
        """一次连接内顺序执行白名单子集，查完即关（PRD §8.4）。"""
        conn = await self._connect()
        try:
            out: dict[str, str] = {}
            for name in names:
                result = await with_timeout(
                    conn.run(COMMANDS[name], check=False),
                    settings.ssh_command_timeout,
                    resource=self._host,
                )
                out[name] = result.stdout or ""
            return out
        finally:
            conn.close()  # asyncssh: 幂等；配合 wait_closed 释放干净
            try:
                await conn.wait_closed()
            except Exception:  # noqa: BLE001 - 关闭阶段的异常不影响主流程
                pass

    async def get_metrics(self) -> dict[str, Any]:
        out = await self._collect(
            ["cpu", "load", "cores", "memory", "network", "disk_usage", "disk_inode"]
        )
        cores_raw = out.get("cores", "")
        return {
            "cpu": {**parse_cpu(out["cpu"]), "cores": int(cores_raw) if cores_raw.strip().isdigit() else None},
            "load": parse_load(out["load"]),
            "memory": parse_memory(out["memory"]),
            "network": parse_network(out["network"]),
            "disk": merge_disk(parse_df(out["disk_usage"]), parse_df(out["disk_inode"])),
        }

    async def run_test(self) -> str:
        """连通性测试（PRD §13.2）：连接成功 + 认证成功 + 白名单命令可执行。"""
        out = await self._collect(["cores"])
        cores = out.get("cores", "").strip()
        return f"SSH OK, {cores or '?'} cores"

    async def health_check(self) -> dict[str, Any]:
        """后台轻量检查（PRD §16）：仅 cpu+memory 两条命令，阈值判定。

        返回含结构化 cpu_pct/mem_pct（overview 任务用于趋势采样）。
        """
        from .diagnosis import diagnose

        out = await self._collect(["cpu", "memory"])
        metrics = {
            "cpu": parse_cpu(out["cpu"]),
            "memory": parse_memory(out["memory"]),
            "disk": [],
            "load": {},
        }
        mem = metrics["memory"]
        mem_pct = (round(mem["used"] / mem["total"] * 100, 1)
                   if mem.get("total") and mem.get("used") is not None else None)
        result = diagnose(metrics)
        return {
            "status": result["status"],
            "message": f"cpu {metrics['cpu']['usage']}%, mem {round(mem_pct) if mem_pct is not None else '?'}%",
            "cpu_pct": metrics["cpu"]["usage"],
            "mem_pct": mem_pct,
        }

    async def get_processes(self) -> list[dict[str, Any]]:
        out = await self._collect(["processes"])
        return parse_processes(out["processes"])

    async def get_disk(self) -> list[dict[str, Any]]:
        out = await self._collect(["disk_usage", "disk_inode"])
        return merge_disk(parse_df(out["disk_usage"]), parse_df(out["disk_inode"]))
