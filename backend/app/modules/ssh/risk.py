"""SSH 脚本/命令风险管控（PRD 外补充，2026-10-23）。

两级管控：
- BLOCK  直接拒绝执行（含保存前预检），oplog 记 BLOCKED——根级毁灭/整机不可用类；
- WARN   执行前需人工二次确认（前端弹确认框 + 请求带 confirm_risk=true），
         定时任务无人工环节，仅受 BLOCK 约束。

规则故意从窄：BLOCK 只拦"绝对不该在内网工具里出现"的命令；WARN 宁可误报
（一次确认成本极低）。检测在**后端**做（前端预检只为 UX，可被绕过），
service 层统一走 assess()，四个执行入口全覆盖。
"""

import re
from typing import NamedTuple


class RiskHit(NamedTuple):
    level: str  # "block" | "warn"
    desc: str


# BLOCK：根级毁灭 / 整机不可用 / 批量不可逆 —— 内网工具无任何正当理由执行
BLOCK_RULES: list[tuple[str, str]] = [
    (r"rm\s+[^|;&\n]*-{1,2}\w*(?:no-preserve-root)\w*", "rm --no-preserve-root"),
    (r"rm\s+[^|;&\n]*\s/(?:\s|$|&|;)", "rm 目标为根路径"),
    (r"rm\s+[^|;&\n]*\s/(?:\*|usr|etc|var|home|boot)(?=\s|$|&|;)", "rm 目标为系统目录"),
    # 递归 rm + 通配符/家目录/当前目录：rm -rf *（经典事故，用户点名必须 BLOCK）
    (r"rm\s+[^|;&\n]*-\w*(?:r|R)\w*[^|;&\n]*\s+(?:\*|\.?\*|~/?\*?)(?=\s|$|&|;)", "rm 递归删除通配符/家目录"),
    (r"rm\s+[^|;&\n]*-\w*(?:r|R)\w*[^|;&\n]*\s+\.{1,2}(?=\s|$|/)", "rm 递归删除当前/上级目录"),
    (r"\bmkfs(?:\.\w+)?\b", "格式化文件系统 (mkfs)"),
    (r"\bdd\b[^|;&\n]*of=/dev/(?:sd|vd|nvme|hd)", "dd 覆写块设备"),
    (r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", "fork 炸弹"),
    (r"(?:^|[;&]\s*|\|\s*)\b(?:shutdown|reboot|halt|poweroff)\b", "关机/重启"),
    (r"\binit\s+[06]\b", "init 0/6（关机/重启）"),
    (r"chmod\s+[^|;&\n]*-R[^|;&\n]*\s+777\s+/(?:\s|$)", "递归 777 根目录"),
    (r">\s*/dev/(?:sd|vd|nvme|hd)", "重定向覆写块设备"),
    # 下载即执行：远程代码直进 shell
    (r"\b(?:curl|wget)\b[^|;&\n]*\|\s*(?:ba|z)?sh\b", "下载并执行远程脚本 (curl|sh)"),
    # find 从根遍历 + 删除
    (r"\bfind\s+/(?:\s|$)[^|;&\n]*(?:-delete\b|-exec\s+rm\b)", "find 从根目录遍历删除"),
    # docker 批量/毁灭类（用户点名：docker 出问题的尽量高危别让执行）
    (r"\bdocker\s+(?:stop|kill|rm)\b[^|;&\n]*\$\(", "docker 批量操作容器 ($()"),
    (r"\bdocker\s+system\s+prune\b[^|;&\n]*-a\b", "docker system prune -a（含未用镜像）"),
    (r"\bdocker\s+volume\s+prune\b", "docker volume prune（删未用卷）"),
    (r"\bdocker\s+rmi\s+-f\s+\$\( docker", "docker 批量删镜像"),
]

# WARN：破坏性但可能有正当场景（清理日志目录等），需人工确认
WARN_RULES: list[tuple[str, str]] = [
    # rm 后（允许先带其他参数）出现 -r/-R 开头的旗标：rm -rf / rm -fr / rm -r / rm --recursive
    (r"\brm\s+(?:[^|;&\n]*\s)?-\w*(?:r|R)\w*", "递归删除 (rm -r)"),
    (r"\brm\s+(?:[^|;&\n]*\s)?-\w*f", "强制删除 (rm -f)"),
    (r"\bfind\b[^|;&\n]*-delete\b", "find -delete 批量删除"),
    (r"\bkillall\b", "killall 批量杀进程"),
    (r"\bpkill\b", "pkill 杀进程"),
    (r"\btruncate\s+-s\s*0?\s", "truncate 清空文件"),
    (r"\bchmod\s+[^|;&\n]*-R\b", "递归改权限 (chmod -R)"),
    (r"\bchown\s+[^|;&\n]*-R\b", "递归改属主 (chown -R)"),
    (r"\biptables\s+(-F|--flush)\b", "清空防火墙规则"),
    (r"\bdocker\s+system\s+prune\b", "docker 清理（含未用镜像/卷）"),
]


def assess(content: str) -> list[RiskHit]:
    """扫描脚本内容，返回命中的风险规则（block 在前）。多行整体扫（规则含 ^ 锚定时按行更有意义，
    但当前规则集无行锚定，整体扫足够）。"""
    text = content or ""
    hits: list[RiskHit] = []
    seen: set[str] = set()
    for level, rules in (("block", BLOCK_RULES), ("warn", WARN_RULES)):
        for pat, desc in rules:
            if desc in seen:
                continue
            if re.search(pat, text, re.IGNORECASE):
                hits.append(RiskHit(level, desc))
                seen.add(desc)
    return hits


def block_descs(hits: list[RiskHit]) -> list[str]:
    return [h.desc for h in hits if h.level == "block"]


def warn_descs(hits: list[RiskHit]) -> list[str]:
    return [h.desc for h in hits if h.level == "warn"]
