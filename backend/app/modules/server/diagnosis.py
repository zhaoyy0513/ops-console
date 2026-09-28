"""Server 诊断引擎（PRD §8.6）：阈值判定 -> {status, issues[]}。

纯函数，不做 IO；阈值由调用方合并后传入（T14：资源 > 站点 > 全局默认）。
"""

from typing import Any

# 全局默认阈值（百分比）
GLOBAL_DEFAULTS: dict[str, int] = {
    "cpu_warning": 80,
    "cpu_critical": 90,
    "memory_warning": 80,
    "memory_critical": 90,
    "disk_warning": 85,
    "disk_critical": 95,
}

_SEVERITY_ORDER = {"HEALTHY": 0, "WARNING": 1, "CRITICAL": 2}


def merge_thresholds(resource: dict | None = None, site: dict | None = None) -> dict[str, int]:
    """阈值三层合并：资源级 > 站点级 > 全局默认，缺层回退（PRD §8.6）。"""
    merged = dict(GLOBAL_DEFAULTS)
    if site:
        merged.update({k: v for k, v in site.items() if k in GLOBAL_DEFAULTS})
    if resource:
        merged.update({k: v for k, v in resource.items() if k in GLOBAL_DEFAULTS})
    return merged


def _issue(issues: list, warning: int, critical: int, value: float,
           itype: str, message_critical: str, message_warning: str,
           extra: dict | None = None) -> None:
    severity = "CRITICAL" if value >= critical else "WARNING" if value >= warning else None
    if severity:
        # 消息模板中的 {value} 在此格式化（模板在调用处传入，调用处拿不到 value）
        msg = (message_critical if severity == "CRITICAL" else message_warning).replace(
            "{value}", str(value))
        issue = {
            "type": itype,
            "severity": severity,
            "value": value,
            "threshold": critical if severity == "CRITICAL" else warning,
            "message": msg,
        }
        if extra:
            issue.update(extra)
        issues.append(issue)


def diagnose(metrics: dict[str, Any], thresholds: dict[str, int] | None = None) -> dict[str, Any]:
    t = merge_thresholds(thresholds)
    issues: list[dict[str, Any]] = []

    cpu = metrics.get("cpu") or {}
    usage = cpu.get("usage")
    if usage is not None:
        _issue(issues, t["cpu_warning"], t["cpu_critical"],
               usage, "CPU_HIGH",
               "CPU 使用率 {value}%，已严重过高", "CPU 使用率 {value}%，偏高")

    mem = metrics.get("memory") or {}
    total, used = mem.get("total"), mem.get("used")
    if total and used is not None:
        _issue(issues, t["memory_warning"], t["memory_critical"],
               round(used / total * 100, 1), "MEMORY_HIGH",
               "内存使用率 {value}%，已严重过高", "内存使用率 {value}%，偏高")

    for disk in metrics.get("disk") or []:
        pct = disk.get("use_percent")
        if pct is None:
            continue
        mount = disk.get("mount", "?")
        _issue(issues, t["disk_warning"], t["disk_critical"],
               pct, "DISK_HIGH",
               f"磁盘 {mount} 使用率 {{value}}%，已严重过高",
               f"磁盘 {mount} 使用率 {{value}}%，偏高",
               extra={"mount": mount})

    # Load 不用固定阈值：load1 超过核数说明有任务在排队（PRD §8.6）
    cores = cpu.get("cores")
    load1 = (metrics.get("load") or {}).get("load1")
    if cores and load1 is not None:
        if load1 >= cores * 2:
            issues.append({
                "type": "LOAD_HIGH", "severity": "CRITICAL", "value": load1,
                "threshold": cores * 2,
                "message": f"系统负载 {load1}，达到 CPU 核数（{cores}）的 2 倍以上——大量任务在排队，机器已严重过载",
            })
        elif load1 >= cores:
            issues.append({
                "type": "LOAD_HIGH", "severity": "WARNING", "value": load1,
                "threshold": cores,
                "message": f"系统负载 {load1}，超过 CPU 核数（{cores}）——平均有 {load1:.1f} 个任务在抢 {cores} 个核心，部分任务在排队等待 CPU",
            })

    status = max((i["severity"] for i in issues), key=lambda s: _SEVERITY_ORDER[s],
                 default="HEALTHY")
    return {"status": status, "issues": issues}
