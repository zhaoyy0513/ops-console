"""MQ 模块：Jolokia provider + 诊断 + backlog 趋势采样（PRD §9）。

采样语义（2026-09-30 调整）：不再有后台定时采样——趋势样本随 get_queues
的真实拉取产生（MQ 页面 3s 轮询 / 手动刷新驱动），与 Server 趋势
"页面在场才采样"同语义。无人查看时无写入，遗留采样 key 靠写时 2h TTL
自然消亡。历史背景：曾有 60s 全量后台采样，24h 空转写 ~5800 序列、
95% 样本（100 点保留 vs 1m/5m 窗口）无读者，已删。
"""

from fastapi import FastAPI

from . import service
from .api import router


def register_module(app: FastAPI) -> None:
    app.include_router(router, prefix="/api")
    service.register_tester()
