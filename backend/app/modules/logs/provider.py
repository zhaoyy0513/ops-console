"""日志查看器 SSH Provider（P1-11）。

只读、按字节窗口读取：单次成本与日志文件大小无关（tail -c / head -n）。
路径只来自站点日志源白名单（service 查库后传入），拼接命令前一律 shlex.quote；
关键词同样 quote。前端无法传入任意命令或未配置的路径。

命令与解析都是纯函数，测试不需要真实 SSH。
"""

import shlex
from typing import Any

import asyncssh

from backend.app.core.config import settings
from backend.app.shared.errors import OpsError
from backend.app.shared.timeout import with_timeout

# 单次返回上限 256KB（超出截断并标记 truncated）
MAX_OUTPUT_BYTES = 256 * 1024
# 打开末尾时先取最后 512KB，再截最后 N 行
TAIL_WINDOW = 512 * 1024
# 搜索只扫最后 2MB（不做全文件检索）
SEARCH_WINDOW = 2 * 1024 * 1024
SEARCH_MAX_MATCHES = 100
DEFAULT_LINES = 200
MAX_LINES = 1000

# 首行标记：错误标记独占首行；成功时首行是 __LOGS_META__<size> <inode> <start> <window_bytes>
META = "__LOGS_META__"
NOT_FOUND = "__LOGS_NOT_FOUND__"
NO_PERM = "__LOGS_NO_PERM__"
NOT_FILE = "__LOGS_NOT_FILE__"
STAT_FAIL = "__LOGS_STAT_FAIL__"
NOT_DIR = "__LOGS_NOT_DIR__"
LIST_META = "__LOGS_LIST__"
MAX_FILES = 500  # 目录列举上限（防超宽目录拖垮输出）

_ERROR_CODES = {
    NOT_FOUND: "NOT_FOUND",
    NO_PERM: "NO_PERMISSION",
    NOT_FILE: "NOT_A_FILE",
    NOT_DIR: "NOT_A_DIR",
    STAT_FAIL: "STAT_FAILED",
}


def clamp_lines(lines: int) -> int:
    return max(1, min(int(lines if lines is not None else DEFAULT_LINES), MAX_LINES))


def build_list_command(dir_path: str) -> str:
    """列出目录下的普通文件（非递归）。只 stat 不读内容——100MB 文件也只是几个字节的元数据。

    用 find -printf 而不是 ls -l：ls 的列宽会随用户名/时间变化，且文件名含空格时无法可靠切分。
    """
    q = shlex.quote(dir_path)
    return (
        f"D={q}\n"
        f'if [ ! -e "$D" ]; then echo {NOT_FOUND}; exit 0; fi\n'
        f'if [ ! -d "$D" ]; then echo {NOT_DIR}; exit 0; fi\n'
        f'if [ ! -r "$D" ] || [ ! -x "$D" ]; then echo {NO_PERM}; exit 0; fi\n'
        f'echo {LIST_META}\n'
        "find \"$D\" -maxdepth 1 -type f -printf '%s\\t%T@\\t%f\\n' 2>/dev/null "
        f'| head -n {MAX_FILES}\n'
    )


def parse_list_output(raw: bytes) -> dict[str, Any]:
    """解析目录列举输出 -> {files: [{name,size,mtime}], truncated, error_code}。

    远端只输出 size/mtime/name 三列（tab 分隔，文件名可含空格）；排序放在本地做，
    避免远端 sort 对 tab 分隔的支持差异。
    """
    nl = raw.find(b"\n")
    header = (raw[:nl] if nl >= 0 else raw).strip().decode("ascii", "replace")
    body = raw[nl + 1:] if nl >= 0 else b""

    if header in _ERROR_CODES:
        return {"files": [], "truncated": False, "error_code": _ERROR_CODES[header], "error": _ERROR_CODES[header]}
    if header != LIST_META:
        return {"files": [], "truncated": False, "error_code": "BAD_RESPONSE", "error": "BAD_RESPONSE"}

    files: list[dict[str, Any]] = []
    for line in body.split(b"\n"):
        if not line:
            continue
        parts = line.decode("utf-8", "replace").split("	", 2)
        if len(parts) < 3:
            continue
        try:
            size = int(parts[0])
            mtime = int(float(parts[1]))
        except ValueError:
            continue
        files.append({"name": parts[2], "size": size, "mtime": mtime})
    files.sort(key=lambda f: f["mtime"], reverse=True)  # 最近修改的在前
    return {
        "files": files,
        "truncated": len(files) >= MAX_FILES,
        "error_code": None,
        "error": None,
    }


def build_read_command(path: str, mode: str, offset: int = 0, kw: str = "",
                       lines: int = DEFAULT_LINES) -> str:
    """构造一次读取的远端命令。

    probe 段先跑：不存在 / 非普通文件 / 不可读 都以首行标记返回，绝不继续读；
    成功时首行输出 __LOGS_META__，其余为日志内容。
    """
    q = shlex.quote(path)
    lines = clamp_lines(lines)
    probe = (
        f"P={q}\n"
        f'if [ ! -e "$P" ]; then echo {NOT_FOUND}; exit 0; fi\n'
        f'if [ ! -f "$P" ]; then echo {NOT_FILE}; exit 0; fi\n'
        f'if [ ! -r "$P" ]; then echo {NO_PERM}; exit 0; fi\n'
        f'SZ=$(stat -c %s "$P" 2>/dev/null) || {{ echo {STAT_FAIL}; exit 0; }}\n'
        f'INODE=$(stat -c %i "$P" 2>/dev/null) || {{ echo {STAT_FAIL}; exit 0; }}\n'
    )
    if mode == "tail":
        body = (
            f'N=$(tail -c {TAIL_WINDOW} "$P" | tail -n {lines} | wc -c)\n'
            f'OFF=$((SZ-N)); [ $OFF -lt 0 ] && OFF=0\n'
            f'echo "{META}$SZ $INODE $OFF $N"\n'
            # 超 256KB 时保留最新的字节（tail -c），后端丢掉被截断的首行片段
            f'tail -c {TAIL_WINDOW} "$P" | tail -n {lines} | tail -c {MAX_OUTPUT_BYTES}\n'
        )
    elif mode == "head":
        body = (
            f'echo "{META}$SZ $INODE 0 0"\n'
            f'head -n {lines} "$P" | head -c {MAX_OUTPUT_BYTES + 1}\n'
        )
    elif mode == "offset":
        off = max(0, int(offset))
        body = (
            f'OFF={off}; [ $OFF -gt $SZ ] && OFF=$SZ\n'
            f'echo "{META}$SZ $INODE $OFF 0"\n'
            # tail -c +N 是 1-based：0-based 偏移 O 对应 O+1
            f'tail -c +$((OFF+1)) "$P" | head -n {lines} | head -c {MAX_OUTPUT_BYTES + 1}\n'
        )
    elif mode == "search":
        kwq = shlex.quote(kw)
        body = (
            f'OFF=$((SZ-{SEARCH_WINDOW})); [ $OFF -lt 0 ] && OFF=0\n'
            f'echo "{META}$SZ $INODE $OFF 0"\n'
            f'tail -c {SEARCH_WINDOW} "$P" | grep -n -i -- {kwq} '
            f'| head -n {SEARCH_MAX_MATCHES + 1} | head -c {MAX_OUTPUT_BYTES + 1}\n'
        )
    else:
        raise ValueError(f"unknown mode: {mode}")
    return probe + body


def _error(code: str) -> dict[str, Any]:
    return {
        "content": "",
        "start_offset": 0,
        "next_offset": 0,
        "size": 0,
        "inode": "",
        "eof": False,
        "truncated": False,
        "error_code": code,
        "error": code,
    }


def parse_read_output(raw: bytes, mode: str) -> dict[str, Any]:
    """解析远端输出：首行标记 + 内容字节。

    返回 {content, start_offset, next_offset, size, inode, eof, truncated,
    error_code, error}。start_offset = 本次内容首字节在文件中的偏移；
    next_offset = 内容末字节之后的位置（跟随模式从它继续读）。
    """
    nl = raw.find(b"\n")
    header = raw[:nl] if nl >= 0 else raw
    body = raw[nl + 1:] if nl >= 0 else b""
    marker = header.strip().decode("ascii", "replace")

    if marker in _ERROR_CODES:
        return _error(_ERROR_CODES[marker])
    if not marker.startswith(META):
        return _error("BAD_RESPONSE")
    try:
        size_s, inode, off_s, n_s = marker[len(META):].split()[:4]
        size, off, window_bytes = int(size_s), int(off_s), int(n_s)
    except (ValueError, IndexError):
        return _error("BAD_RESPONSE")

    truncated = False
    if mode == "tail":
        raw_len = len(body)
        if window_bytes > MAX_OUTPUT_BYTES:
            truncated = True
            # 远端保留的是最后 256KB，首行可能是半行：丢掉它并把起点后移
            idx = body.find(b"\n")
            skip = idx + 1 if idx >= 0 else 0
            body = body[skip:]
            start = max(0, size - raw_len) + skip
        else:
            start = max(0, size - raw_len)
        nxt = size
        eof = True
    elif mode == "search":
        rows = body.split(b"\n")
        if rows and rows[-1] == b"":
            rows.pop()
        if len(rows) > SEARCH_MAX_MATCHES:
            truncated = True
            rows = rows[:SEARCH_MAX_MATCHES]
        body = b"\n".join(rows) + (b"\n" if rows else b"")
        if len(body) > MAX_OUTPUT_BYTES:
            truncated = True
            body = body[:MAX_OUTPUT_BYTES]
        start = off
        nxt = size
        eof = True
    else:  # head / offset
        if len(body) > MAX_OUTPUT_BYTES:
            truncated = True
            body = body[:MAX_OUTPUT_BYTES]
        # 跟随/翻页只前进到最后一个完整行，半行留给下一次读（避免把一行劈成两半）
        cut = body.rfind(b"\n") + 1
        if 0 < cut < len(body):
            body = body[:cut]
        start = off if mode == "offset" else 0
        nxt = start + len(body)
        eof = nxt >= size

    return {
        "content": body.decode("utf-8", errors="replace"),
        "start_offset": start,
        "next_offset": nxt,
        "size": size,
        "inode": inode,
        "eof": eof,
        "truncated": truncated,
        "error_code": None,
        "error": None,
    }


class SSHLogsProvider:
    """一次读取 = 一次连接、一条命令、查完即关（与 server provider 同策略）。"""

    def __init__(self, config: dict[str, Any]):
        self._host: str = config["host"]
        self._port: int = int(config.get("port") or 22)
        self._username: str = config.get("username") or ""
        self._password: str = config.get("password") or ""
        self._private_key: str = config.get("private_key") or ""

    async def _connect(self):
        # ponytail: known_hosts=None 与 server provider 一致（内部工具）；有安全要求时换 known_hosts
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
            raise OpsError("AUTH_FAILED", f"SSH auth failed: {e}", self._host) from None
        except (asyncssh.Error, OSError) as e:
            raise OpsError(
                "REMOTE_CONNECTION_FAILED", f"SSH connect failed: {e}", self._host
            ) from None

    async def list_files(self, dir_path: str) -> dict[str, Any]:
        """列目录：一次连接、一条命令。失败以 in-band error_code 返回，不抛 5xx。"""
        cmd = build_list_command(dir_path)
        conn = await self._connect()
        try:
            result = await with_timeout(
                conn.run(cmd, check=False, encoding=None),
                settings.ssh_command_timeout,
                resource=self._host,
            )
            raw = result.stdout or b""
        finally:
            conn.close()
            try:
                await conn.wait_closed()
            except Exception:  # noqa: BLE001
                pass
        return parse_list_output(raw)

    async def read(self, path: str, *, mode: str = "tail", offset: int = 0,
                   kw: str = "", lines: int = DEFAULT_LINES) -> dict[str, Any]:
        cmd = build_read_command(path, mode, offset, kw, lines)
        conn = await self._connect()
        try:
            result = await with_timeout(
                conn.run(cmd, check=False, encoding=None),
                settings.ssh_command_timeout,
                resource=self._host,
            )
            raw = result.stdout or b""
            stderr = (result.stderr or b"").decode("utf-8", "replace").strip()
        finally:
            conn.close()  # asyncssh: 幂等
            try:
                await conn.wait_closed()
            except Exception:  # noqa: BLE001 - 关闭阶段异常不影响主流程
                pass
        out = parse_read_output(raw, mode)
        if out["error_code"] == "BAD_RESPONSE" and stderr:
            out["error"] = stderr[:300]
        return out
