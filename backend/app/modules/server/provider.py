"""SSH 只读诊断 Provider（PRD §8/§10）。

后端内部实现细节：固定白名单命令、按需连接查完即关（Decision 004）。
本模块对外只暴露结构化数据——前端不感知命令，也无法传入任何命令。
"""

import re
import time
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
    # top -bn2 第二帧才是瞬时 CPU%（ps aux 的 %CPU 是进程生命周期平均，基本不动）
    # -c 显示完整命令行（默认会截断）
    "processes": "LC_ALL=C top -bn2 -c -w 512",
    # 僵尸进程：STAT（第 3 列）含 Z 即僵尸；comm 为可执行名（完整命令行见 processes）
    "zombies": "LC_ALL=C ps -eo pid,ppid,stat,comm | awk '$3 ~ /Z/'",
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


def parse_zombies(text: str) -> list[dict[str, Any]]:
    """ps 僵尸行（awk 已过滤）-> [{pid, ppid, stat, comm}]，comm 可含空格故只切 3 刀。"""
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        try:
            rows.append(
                {
                    "pid": int(parts[0]),
                    "ppid": int(parts[1]),
                    "stat": parts[2],
                    "comm": parts[3],
                }
            )
        except ValueError:
            continue
    return rows


def parse_processes(text: str) -> list[dict[str, Any]]:
    """top -bn2 输出 -> [{pid, command, cpu_percent, mem_percent}]（取第二帧=瞬时值）。"""
    frames = text.split("top - ")
    body = frames[-1] if len(frames) > 1 else text
    lines = body.splitlines()
    start = next((i for i, l in enumerate(lines) if l.strip().startswith("PID ")), None)
    if start is None:
        return []
    rows: list[dict[str, Any]] = []
    for line in lines[start + 1:]:
        parts = line.split(None, 11)
        if len(parts) < 12:
            continue
        try:
            rows.append(
                {
                    "pid": int(parts[0]),
                    "cpu_percent": float(parts[8]),
                    "mem_percent": float(parts[9]),
                    "command": parts[11],
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
        except asyncssh.PermissionDenied as e:
            # 认证失败不可重试（AUTH_FAILED 不在 RETRYABLE_CODES）：重试只会
            # 翻倍认证尝试，纯喂 fail2ban；连接拒绝/超时仍走可重试分支
            raise OpsError("AUTH_FAILED", f"SSH auth failed: {e}", self._host) from None
        except (asyncssh.Error, OSError) as e:
            raise OpsError(
                "REMOTE_CONNECTION_FAILED", f"SSH connect failed: {e}", self._host
            ) from None

    async def _run(self, commands: list[str]) -> list[str]:
        """一次连接内顺序执行命令，查完即关（PRD §8.4）。

        整体预算 = 单命令超时 × 命令数：一条挂死命令（如 NFS 上的 df）
        不再各自耗满 10s×N 条，后续命令只分到剩余预算，整次采集有界，
        上层重试也因此有界。
        """
        conn = await self._connect()
        try:
            out: list[str] = []
            deadline = time.monotonic() + settings.ssh_command_timeout * max(1, len(commands))
            for cmd in commands:
                remaining = max(deadline - time.monotonic(), 0)
                result = await with_timeout(
                    conn.run(cmd, check=False),
                    remaining,
                    resource=self._host,
                )
                out.append(result.stdout or "")
            return out
        finally:
            conn.close()  # asyncssh: 幂等；配合 wait_closed 释放干净
            try:
                await conn.wait_closed()
            except Exception:  # noqa: BLE001 - 关闭阶段的异常不影响主流程
                pass

    async def _collect(self, names: list[str]) -> dict[str, str]:
        """白名单子集执行：命令取自模块常量表，非用户输入。"""
        outs = await self._run([COMMANDS[name] for name in names])
        return dict(zip(names, outs, strict=True))

    async def get_metrics(self) -> dict[str, Any]:
        out = await self._collect(
            ["cpu", "load", "cores", "memory", "network", "disk_usage", "disk_inode", "zombies"]
        )
        cores_raw = out.get("cores", "")
        zombies = parse_zombies(out["zombies"])
        return {
            "cpu": {**parse_cpu(out["cpu"]), "cores": int(cores_raw) if cores_raw.strip().isdigit() else None},
            "load": parse_load(out["load"]),
            "memory": parse_memory(out["memory"]),
            "network": parse_network(out["network"]),
            "disk": merge_disk(parse_df(out["disk_usage"]), parse_df(out["disk_inode"])),
            "zombie_count": len(zombies),
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

    async def get_zombies(self) -> list[dict[str, Any]]:
        out = await self._collect(["zombies"])
        return parse_zombies(out["zombies"])

    async def kill_zombie(self, pid: int) -> None:
        """kill -9 指定进程：本模块唯一写命令。pid 已在上层正则校验为纯数字，
        用户无法借 path 参数注入任意命令（保持"前端不感知命令"的白名单原则）。"""
        await self._run([f"kill -9 {pid}"])

    async def get_disk(self) -> list[dict[str, Any]]:
        out = await self._collect(["disk_usage", "disk_inode"])
        return merge_disk(parse_df(out["disk_usage"]), parse_df(out["disk_inode"]))
