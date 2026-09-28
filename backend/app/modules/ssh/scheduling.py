"""SSH 脚本定时调度（APScheduler，平台内执行——设计取舍见 service.py 模块注释）。

job id 规范：ssh:{site_id}:{script_id}；脚本删除/禁用即自动注销。
后端启动时 restore_all() 从配置恢复全部 enabled+cron 脚本的调度。
"""

from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.app.core.redis import get_platform_redis

_scheduler: AsyncIOScheduler | None = None


def _job_id(site_id: str, script_id: str) -> str:
    return f"ssh:{site_id}:{script_id}"


async def iter_scheduled_scripts():
    """遍历全部站点中 (site_id, script)——cron 非空且 sched_enabled 的脚本。"""
    from backend.app.modules.sites.service import list_sites
    from backend.app.modules.ssh.service import _key

    r = get_platform_redis()
    for site in await list_sites():
        raw = await r.hvals(_key(site["id"]))
        for x in raw:
            import json

            script = json.loads(x)
            if script.get("cron") and script.get("sched_enabled"):
                yield site["id"], script


def sync_one(site_id: str, script: dict[str, Any]) -> None:
    """按脚本当前状态同步其定时 job（新增/修改/开关/删除后调用）。"""
    if _scheduler is None:
        return
    from backend.app.modules.ssh.service import run_script

    jid = _job_id(site_id, script["id"])
    if _scheduler.get_job(jid):
        _scheduler.remove_job(jid)
    if script.get("cron") and script.get("sched_enabled"):
        _scheduler.add_job(
            run_script,
            CronTrigger.from_crontab(script["cron"]),
            args=[site_id, script["id"]],
            id=jid,
            replace_existing=True,
            misfire_grace_time=300,
        )


def unschedule(site_id: str, script_id: str) -> None:
    if _scheduler is not None:
        jid = _job_id(site_id, script_id)
        if _scheduler.get_job(jid):
            _scheduler.remove_job(jid)


async def restore_all() -> None:
    """后端启动时从配置恢复全部定时脚本（幂等）。"""
    count = 0
    async for site_id, script in iter_scheduled_scripts():
        sync_one(site_id, script)
        count += 1
    print(f"[ssh] restored {count} scheduled script jobs")


def attach_scheduler(app) -> None:
    """挂到应用 lifespan（同 mq 模块模式）；并做启动恢复。"""
    from contextlib import asynccontextmanager

    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = AsyncIOScheduler()
    prev = app.router.lifespan_context

    @asynccontextmanager
    async def ctx(a):
        async with prev(a):
            _scheduler.start()
            await restore_all()
            try:
                yield
            finally:
                if _scheduler.running:
                    _scheduler.shutdown(wait=False)

    app.router.lifespan_context = ctx


# 延迟 import 避免循环（scheduling 由 api/__init__ 调用）
from backend.app.core.redis import get_platform_redis  # noqa: E402
