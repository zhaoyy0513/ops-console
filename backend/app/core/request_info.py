"""调用者上下文（无用户管理下的轻量溯源）。

中间件从请求头提取 IP / 操作人别名，写入 contextvar；oplog.record 落日志时自动读取。
选 contextvar 而非显式传参的原因：oplog.record 有 20+ 调用点，显式传参要把
Request（或 IP 串）穿透 service 层每一层签名——contextvar 让调用点零改动。

MAC 地址说明：MAC 是二层地址，跨路由/经 nginx 反代后服务端不可见，无法采集；
操作人别名（前端设置一次，随请求头携带）+ IP 组合即可定位到人。
"""

from contextvars import ContextVar

# 默认 "-"：定时任务等无 HTTP 上下文的路径（APScheduler 触发）落日志仍成立
caller_ip_var: ContextVar[str] = ContextVar("caller_ip", default="-")
caller_var: ContextVar[str] = ContextVar("caller_user", default="-")


def set_caller(ip: str, user: str) -> None:
    caller_ip_var.set(ip)
    caller_var.set(user)


def get_caller() -> tuple[str, str]:
    """返回 (操作人别名, IP)。"""
    return caller_var.get(), caller_ip_var.get()
