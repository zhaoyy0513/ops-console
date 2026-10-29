"""SSH 只读诊断 Provider（PRD §8/§10）。

后端内部实现细节：固定白名单命令、按需连接查完即关（Decision 004）。
本模块对外只暴露结构化数据——前端不感知命令，也无法传入任何命令。
"""

import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

import asyncssh

from backend.app.core.config import settings
from backend.app.shared.errors import OpsError
from backend.app.shared.timeout import with_timeout

# 能力探测：全部极轻（test/command -v），与其它命令在同一 SSH 会话内顺序执行，不额外建连。
# 被纳管机器不保证 root，缺权限/缺命令的项只置空自身，不影响其它指标。
# 这些同样是只读命令，故一并登记进 COMMANDS（白名单是「可执行命令」的唯一真相）。
CAP_COMMANDS: dict[str, str] = {
    "uid": "id -u",
    "psi": "test -r /proc/pressure/cpu && echo ok || echo no",
    "dmesg": "dmesg -T >/dev/null 2>&1 && echo ok || echo no",
    "systemctl": "command -v systemctl >/dev/null 2>&1 && echo ok || echo no",
    "kernlog": "test -r /var/log/kern.log && echo ok || echo no",
    "syslog": "test -r /var/log/syslog && echo ok || echo no",
}

# 只读诊断命令白名单：模块常量，非用户输入。LC_ALL=C 保证输出格式可解析。
COMMANDS: dict[str, str] = {
    # top -bn2 取第二帧：首帧是 top 自身启动后的亚秒瞬时值，单核一冲就显示 100%（噪声）；
    # -d 1 让第二帧成为约 1 秒的真实平均。多帧时 parse_cpu 取最后一帧
    "cpu": "LC_ALL=C top -bn2 -d 1 | head -14",
    "load": "LC_ALL=C uptime",
    "cores": "nproc",
    "memory": "LC_ALL=C free -m",
    "disk_usage": "LC_ALL=C df -hP",
    "disk_inode": "LC_ALL=C df -iP",
    "network": "cat /proc/net/dev",
    # 磁盘 IO：读计数/扇区（/proc/diskstats 常驻内存，无额外负载）
    "disk_io": "cat /proc/diskstats",
    # top -bn2 第二帧才是瞬时 CPU%（ps aux 的 %CPU 是进程生命周期平均，基本不动）
    # -c 显示完整命令行（默认会截断）
    "processes": "LC_ALL=C top -bn2 -c -w 512",
    # 僵尸采集：全量 ps，Python 解析过滤（awk 已弃）。僵尸自身 cmdline 为空，
    # 完整命令行取自未收尸的父进程（同份输出内解析）
    "zombies": "LC_ALL=C ps -eo pid,ppid,stat,args",
    # 启动时间：容器内 /var/run/utmp 常为空 -> 输出空，parse_boot_time 返回 None
    "boot_time": "LC_ALL=C who -b 2>/dev/null",
    # 文件句柄：世界可读，无权限要求
    "file_nr": "cat /proc/sys/fs/file-nr",
    # PSI 压力：仅在 capabilities.psi 为真时执行；io/memory 在个别内核上缺失 -> 空输出
    "psi_cpu": "cat /proc/pressure/cpu 2>/dev/null",
    "psi_io": "cat /proc/pressure/io 2>/dev/null",
    "psi_memory": "cat /proc/pressure/memory 2>/dev/null",
    # 失败单元：&& echo __OK__ 标记成败——systemctl 存在但 systemd 未运行（容器）时无标记，
    # 前端显示「不可用」而不是误报 0 个失败单元
    "failed_units": "LC_ALL=C systemctl --failed --no-legend --plain 2>/dev/null && echo __OK__",
    # OOM：三路日志源按能力择一（见 OOM_SOURCES），全部限定尾部 256KB 窗口避免读整份大日志
    "oom_dmesg": "dmesg -T 2>/dev/null | grep -iE 'out of memory|killed process' | tail -5",
    "oom_kernlog": "tail -c 262144 /var/log/kern.log 2>/dev/null | grep -iE 'out of memory|killed process' | tail -5",
    "oom_syslog": "tail -c 262144 /var/log/syslog 2>/dev/null | grep -iE 'out of memory|killed process' | tail -5",
    **CAP_COMMANDS,
}

# metrics 基础命令（任一失败即整次失败：这些是页面主指标，缺了没法看）
BASE_COMMANDS = [
    "cpu", "load", "cores", "memory", "network", "disk_usage", "disk_inode", "disk_io", "zombies",
]

# OOM 日志源优先级：(能力名, 命令名)。取第一个可读来源，命中即止
OOM_SOURCES = [("dmesg", "oom_dmesg"), ("kernlog", "oom_kernlog"), ("syslog", "oom_syslog")]

# PSI 三类资源；cpu 通常只有 some 行，io/memory 可能同时有 some/full
PSI_RESOURCES = ("cpu", "io", "memory")


# ---------- 解析器（纯函数；字段缺失返回 None，不让单条解析拖垮整体） ----------


def parse_cpu(text: str) -> dict[str, float | None]:
    """top 输出 -> {usage, iowait, steal}，usage = 100 - idle。多帧输出取最后一帧（首帧是亚秒噪声）。

    steal 是虚拟化环境里被宿主机/其它租户抢走的 CPU 时间：本机负载低但 steal 高，
    说明慢不是自己的问题。
    """
    idle = re.findall(r"(\d+\.?\d*)\s*id[, ]", text)
    wa = re.findall(r"(\d+\.?\d*)\s*wa[, ]", text)
    # st 是 Cpu 行最后一列（行尾无逗号），不能用 [, ] 收尾，用 \b
    st = re.findall(r"(\d+\.?\d*)\s*st\b", text)
    return {
        "usage": round(100 - float(idle[-1]), 1) if idle else None,
        "iowait": float(wa[-1]) if wa else None,
        "steal": float(st[-1]) if st else None,
    }


def parse_load(text: str) -> dict[str, float | None]:
    """uptime 输出 -> {load1, load5, load15}。"""
    m = re.search(r"load average:\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)", text)
    if not m:
        return {"load1": None, "load5": None, "load15": None}
    return {"load1": float(m.group(1)), "load5": float(m.group(2)), "load15": float(m.group(3))}


def parse_uptime_text(text: str) -> str | None:
    """uptime 输出里提取 `up ...` 片段（原样文本，如 "37 days, 4:21"）。"""
    m = re.search(r"\bup\s+(.+?),\s+\d+\s+users?,\s+load average", text) or re.search(
        r"\bup\s+(.+?),\s+load average", text
    )
    # 原始输出里日期与时间之间是两个空格，压成单空格便于展示
    return " ".join(m.group(1).split()) if m else None


def parse_boot_time(text: str) -> str | None:
    """who -b -> "system boot  2026-10-20 10:12" -> ISO 8601（无时区）；容器内常为空 -> None。"""
    m = re.search(r"(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})(?::(\d{2}))?", text)
    if not m:
        return None
    return f"{m.group(1)}T{m.group(2)}:{m.group(3) or '00'}"


def parse_file_nr(text: str) -> dict[str, Any] | None:
    """/proc/sys/fs/file-nr -> {allocated, max, percent}。三列：已分配 / 已分配未用 / 上限。"""
    parts = text.split()
    if len(parts) < 3:
        return None
    try:
        allocated, maximum = int(parts[0]), int(parts[2])
    except ValueError:
        return None
    if maximum <= 0:
        return None
    return {"allocated": allocated, "max": maximum, "percent": round(allocated / maximum * 100, 1)}


def parse_capabilities(texts: dict[str, str]) -> dict[str, bool]:
    """能力探测输出 -> {root, psi, dmesg, systemctl, kernlog, syslog}；探测失败一律 False。"""

    def ok(name: str) -> bool:
        return texts.get(name, "").strip().endswith("ok")

    return {
        "root": texts.get("uid", "").strip() == "0",
        "psi": ok("psi"),
        "dmesg": ok("dmesg"),
        "systemctl": ok("systemctl"),
        "kernlog": ok("kernlog"),
        "syslog": ok("syslog"),
    }


# systemd 单元名形如 nginx.service / dev-sda1.device；用它挡掉 stderr 混进来的杂行
_UNIT_RE = re.compile(r"^\S+\.\w+$")

# /proc/pressure/* 每行：`some avg10=0.25 avg60=0.10 avg300=0.05 total=12345`
_PSI_LINE = re.compile(r"^(some|full)\s+avg10=([\d.]+)")


def parse_pressure(text: str) -> dict[str, float | None] | None:
    """单份 /proc/pressure/<res> -> {some, full}（avg10，单位 %）。空/脏数据 -> None。"""
    found: dict[str, float] = {}
    for line in text.splitlines():
        m = _PSI_LINE.match(line.strip())
        if not m:
            continue
        try:
            found[m.group(1)] = float(m.group(2))
        except ValueError:  # avg10=abc 这类脏行：跳过该行，不让整份失败
            continue
    return {"some": found.get("some"), "full": found.get("full")} if found else None


def parse_psi(texts: dict[str, str | None]) -> dict[str, dict[str, float | None] | None] | None:
    """三份压力文件 -> {cpu, io, memory}；全部不可读 -> None（前端整卡隐藏，不报「不可用」）。"""
    rows = {name: parse_pressure(texts.get(name) or "") for name in PSI_RESOURCES}
    return rows if any(rows.values()) else None


def parse_failed_units(text: str) -> list[dict[str, str]]:
    """systemctl --failed --no-legend --plain -> [{unit, description}]。空输出 -> []。"""
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        # 列：UNIT LOAD ACTIVE SUB DESCRIPTION（description 可含空格，只切 4 刀）
        parts = line.split(None, 4)
        if len(parts) < 4 or not _UNIT_RE.match(parts[0]):
            continue
        rows.append({"unit": parts[0], "description": parts[4].strip() if len(parts) > 4 else ""})
    return rows


_DMESG_TS = re.compile(r"^\[([^\]]+)\]\s*")
_SYSLOG_TS = re.compile(r"^(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s")
_KILLED_PROC = re.compile(r"kill(?:ed)? process (\d+) \(([^)]+)\)", re.I)


def parse_oom_events(text: str) -> list[dict[str, Any]]:
    """grep 后的内核日志行 -> [{time, process, detail}]。

    time 尽力而为（dmesg -T 的 [Mon Oct 27 ...] 或 syslog 的 Oct 27 10:12:33 前缀），
    解析不到就 None；process 取被击杀进程名，只有 "out of memory" 无进程名的行给 None。
    """
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        if "out of memory" not in line.lower() and "killed process" not in line.lower():
            continue
        ts = _DMESG_TS.match(line) or _SYSLOG_TS.match(line)
        killed = _KILLED_PROC.search(line)
        rows.append(
            {
                "time": ts.group(1).strip() if ts else None,
                "process": killed.group(2) if killed else None,
                "detail": line.strip()[:300],
            }
        )
    return rows


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


# 非物理盘前缀：loop（回环）/ ram / sr（光驱）/ fd（软驱）——计入会污染 IO 统计
VIRTUAL_DISK = re.compile(r"^(?:loop|ram|sr|fd)\d")


def _is_partition(name: str, all_names: set[str]) -> bool:
    """name 是否为另一个已存在设备的分区。

    兼容两种命名：sda -> sda1（数字后缀）、nvme0n1 -> nvme0n1p1（p+数字）。
    用「同批输出里存在基设备」判定，而非硬编码设备名前缀——容器里常见
    dm-0 / overlay 这类名字，白名单会直接漏采。
    """
    m = re.match(r"^(.+?)(p?)(\d+)$", name)
    if not m:
        return False
    base = m.group(1)
    if base in all_names:
        return True
    # nvme0n1p1：去掉 "p" 后的前缀也要试（nvme0n1 本身以数字结尾）
    return m.group(2) == "p" and base.rstrip("p") in all_names


def parse_diskstats(text: str) -> dict[str, int] | None:
    """/proc/diskstats -> 全盘聚合 {read_bytes, write_bytes, read_iops, write_iops}。

    扇区固定 512B（内核口径）。字段位：name=2、读完成=3、读扇区=5、写完成=7、写扇区=9。
    过滤规则：跳过 loop/ram/sr/fd；跳过分区（否则与整盘双重计数）。
    无任何可用设备（受限容器）返回 None，前端显示 ?。
    """
    rows: list[tuple[str, int, int, int, int]] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 14:
            continue
        try:
            rows.append((parts[2], int(parts[3]), int(parts[5]), int(parts[7]), int(parts[9])))
        except ValueError:
            continue
    names = {r[0] for r in rows}
    reads = writes = riops = wiops = 0
    counted = 0
    for name, r_completed, r_sectors, w_completed, w_sectors in rows:
        if VIRTUAL_DISK.match(name) or _is_partition(name, names):
            continue
        reads += r_sectors
        writes += w_sectors
        riops += r_completed
        wiops += w_completed
        counted += 1
    if not counted:
        return None
    return {
        "read_bytes": reads * 512,
        "write_bytes": writes * 512,
        "read_iops": riops,
        "write_iops": wiops,
    }


def parse_zombies(text: str) -> list[dict[str, Any]]:
    """ps -eo pid,ppid,stat,args 全量输出 -> [{pid, ppid, stat, args}]。

    args 可含空格故只切 3 刀；表头等非数字行跳过，不让单条解析拖垮整体。
    """
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
                    "args": parts[3],
                }
            )
        except ValueError:  # 表头行（PID PPID STAT ARGS）
            continue
    return rows


def group_zombies(text: str) -> dict[str, Any]:
    """stat 以 Z 开头的行视为僵尸，按 ppid 分组 -> {total, groups: [{ppid, count, cmd}]}。

    count 降序（同数按 ppid 升序保证稳定）。cmd = 同一 ps 输出中父进程的 args
    （父进程存活才有僵尸；若父进程已不在输出中则 cmd 为 ''）。
    """
    rows = parse_zombies(text)
    args_by_pid = {r["pid"]: r["args"] for r in rows}
    counts: dict[int, int] = {}
    for r in rows:
        if r["stat"].startswith("Z"):
            counts[r["ppid"]] = counts.get(r["ppid"], 0) + 1
    groups = [
        {"ppid": ppid, "count": n, "cmd": args_by_pid.get(ppid, "")}
        for ppid, n in counts.items()
    ]
    groups.sort(key=lambda g: (-g["count"], g["ppid"]))
    return {"total": sum(counts.values()), "groups": groups}


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


async def _safe(run: Callable[[str], Awaitable[str]], cmd: str) -> str | None:
    """可选诊断项单条容错：权限不足 / 命令不存在 / 超时只让该项为 None，不让整次采集失败。"""
    try:
        return await run(cmd)
    except OpsError:
        return None


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

    @asynccontextmanager
    async def _session(
        self, command_count: int
    ) -> AsyncIterator[Callable[[str], Awaitable[str]]]:
        """一次连接内顺序执行命令，查完即关（PRD §8.4）。

        整体预算 = 单命令超时 × 命令数：一条挂死命令（如 NFS 上的 df）
        不再各自耗满 10s×N 条，后续命令只分到剩余预算，整次采集有界，
        上层重试也因此有界。
        """
        conn = await self._connect()
        try:
            deadline = time.monotonic() + settings.ssh_command_timeout * max(1, command_count)

            async def run(cmd: str) -> str:
                remaining = max(deadline - time.monotonic(), 0)
                result = await with_timeout(
                    conn.run(cmd, check=False),
                    remaining,
                    resource=self._host,
                )
                return result.stdout or ""

            yield run
        finally:
            conn.close()  # asyncssh: 幂等；配合 wait_closed 释放干净
            try:
                await conn.wait_closed()
            except Exception:  # noqa: BLE001 - 关闭阶段的异常不影响主流程
                pass

    async def _run(self, commands: list[str]) -> list[str]:
        async with self._session(len(commands)) as run:
            return [await run(cmd) for cmd in commands]

    async def _collect(self, names: list[str]) -> dict[str, str]:
        """白名单子集执行：命令取自模块常量表，非用户输入。"""
        outs = await self._run([COMMANDS[name] for name in names])
        return dict(zip(names, outs, strict=True))

    async def get_metrics(self) -> dict[str, Any]:
        # 预算按最坏条数估：基础 9 + 能力探测 6 + PSI 3 + who -b / file-nr / 失败单元 / OOM 各 1
        async with self._session(len(BASE_COMMANDS) + len(CAP_COMMANDS) + 7) as run:
            out: dict[str, str] = {}
            for name in BASE_COMMANDS:
                out[name] = await run(COMMANDS[name])  # 主指标：失败即整次失败
            caps = parse_capabilities(
                {name: await _safe(run, cmd) or "" for name, cmd in CAP_COMMANDS.items()}
            )
            boot_raw = await _safe(run, COMMANDS["boot_time"])
            fd_raw = await _safe(run, COMMANDS["file_nr"])
            # PSI：不支持（内核无 CONFIG_PSI）时连命令都不发
            psi_raw = (
                {name: await _safe(run, COMMANDS[f"psi_{name}"]) for name in PSI_RESOURCES}
                if caps["psi"]
                else None
            )
            # 失败单元：systemctl 不可用时连命令都不发（不误报 0 个失败单元）
            failed_raw = await _safe(run, COMMANDS["failed_units"]) if caps["systemctl"] else None
            # OOM：按 dmesg -> kern.log -> syslog 取第一个可读来源（命中即止）
            oom_raw: str | None = None
            for cap, name in OOM_SOURCES:
                if caps[cap]:
                    oom_raw = await _safe(run, COMMANDS[name])
                    if oom_raw is not None:
                        break

        cores_raw = out.get("cores", "")
        zombie_rows = parse_zombies(out["zombies"])
        # 无 __OK__ 标记 = systemctl 存在但不可用（容器内 systemd 未运行），按不可用处理
        failed_units = (
            parse_failed_units(failed_raw) if failed_raw and "__OK__" in failed_raw else None
        )
        return {
            "cpu": {**parse_cpu(out["cpu"]), "cores": int(cores_raw) if cores_raw.strip().isdigit() else None},
            "load": parse_load(out["load"]),
            "memory": parse_memory(out["memory"]),
            "network": parse_network(out["network"]),
            "disk": merge_disk(parse_df(out["disk_usage"]), parse_df(out["disk_inode"])),
            "disk_io": parse_diskstats(out.get("disk_io", "")),
            "zombie_count": sum(1 for r in zombie_rows if r["stat"].startswith("Z")),
            "uptime_text": parse_uptime_text(out["load"]),
            "boot_time": parse_boot_time(boot_raw or ""),
            "fd_usage": parse_file_nr(fd_raw or ""),
            "failed_units": failed_units,
            "failed_units_unavailable": None if failed_units is not None else "no_systemd",
            "oom_events": parse_oom_events(oom_raw) if oom_raw is not None else None,
            "oom_unavailable": None if oom_raw is not None else "need_root_or_adm",
            # 不可用 -> None：前端整卡隐藏（PSI 缺失是环境差异，不是故障）
            "psi": parse_psi(psi_raw) if psi_raw is not None else None,
            "capabilities": caps,
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

    async def get_zombies(self) -> dict[str, Any]:
        out = await self._collect(["zombies"])
        return group_zombies(out["zombies"])

    async def kill_zombie(self, pid: int) -> None:
        """kill -9 指定进程：本模块唯一写命令。pid 已在上层正则校验为纯数字，
        用户无法借 path 参数注入任意命令（保持"前端不感知命令"的白名单原则）。

        `2>&1 && echo __KILL_OK__`：kill 失败（如 SSH 用户非 root 杀不动 root
        进程的 Operation not permitted）时 marker 不会输出 -> 报 REMOTE_KILL_FAILED
        并携带远端 stderr，而不是静默吞掉、oplog 记 SUCCESS。
        """
        (out,) = await self._run([f"kill -9 {pid} 2>&1 && echo __KILL_OK__"])
        if "__KILL_OK__" not in out:
            raise OpsError(
                "REMOTE_KILL_FAILED", f"remote kill failed: {out.strip() or 'no output'}",
                status_code=400,
            )

    async def get_disk(self) -> list[dict[str, Any]]:
        out = await self._collect(["disk_usage", "disk_inode"])
        return merge_disk(parse_df(out["disk_usage"]), parse_df(out["disk_inode"]))
