from backend.app.modules.server.diagnosis import GLOBAL_DEFAULTS, diagnose, merge_thresholds


def _metrics(cpu=None, mem=None, disk=None, load=None, cores=4):
    return {
        "cpu": {"usage": cpu, "cores": cores},
        "memory": mem or {},
        "disk": disk or [],
        "load": load or {},
    }


def test_healthy_when_all_below():
    r = diagnose(_metrics(cpu=50, mem={"total": 100, "used": 50}))
    assert r == {"status": "HEALTHY", "issues": []}


def test_cpu_warning_at_80_critical_at_90():
    assert diagnose(_metrics(cpu=79))["status"] == "HEALTHY"
    r80 = diagnose(_metrics(cpu=80))
    assert r80["status"] == "WARNING"
    assert r80["issues"][0]["type"] == "CPU_HIGH"
    assert r80["issues"][0]["threshold"] == 80
    assert diagnose(_metrics(cpu=89))["status"] == "WARNING"
    r90 = diagnose(_metrics(cpu=90))
    assert r90["status"] == "CRITICAL"
    assert r90["issues"][0]["threshold"] == 90


def test_memory_boundaries():
    mem = {"total": 1000}
    assert diagnose(_metrics(mem={**mem, "used": 799}))["status"] == "HEALTHY"
    assert diagnose(_metrics(mem={**mem, "used": 800}))["status"] == "WARNING"
    assert diagnose(_metrics(mem={**mem, "used": 899}))["status"] == "WARNING"
    assert diagnose(_metrics(mem={**mem, "used": 900}))["status"] == "CRITICAL"


def test_disk_boundaries_per_mount():
    disk = [{"mount": "/data", "use_percent": 84}, {"mount": "/", "use_percent": 85}]
    r = diagnose(_metrics(disk=disk))
    assert r["status"] == "WARNING"
    r = diagnose(_metrics(disk=[{"mount": "/data", "use_percent": 95}]))
    assert r["status"] == "CRITICAL"
    assert r["issues"][0]["message"] == "Disk usage on /data is critical"


def test_load_uses_core_count_not_fixed_threshold():
    # 8 核 load 6：远超默认 cpu 阈值语义，但按核数判断应为 HEALTHY
    assert diagnose(_metrics(cpu=10, load={"load1": 6.0}, cores=8))["status"] == "HEALTHY"
    assert diagnose(_metrics(cpu=10, load={"load1": 8.0}, cores=8))["status"] == "WARNING"
    assert diagnose(_metrics(cpu=10, load={"load1": 16.0}, cores=8))["status"] == "CRITICAL"


def test_worst_status_wins():
    r = diagnose(_metrics(cpu=85, mem={"total": 100, "used": 95}))
    assert r["status"] == "CRITICAL"
    assert {i["type"] for i in r["issues"]} == {"CPU_HIGH", "MEMORY_HIGH"}


def test_missing_fields_no_crash():
    r = diagnose({"cpu": {}, "memory": {}, "disk": [{"mount": "/"}], "load": {}})
    assert r["status"] == "HEALTHY"


def test_merge_thresholds_priority():
    site = {"cpu_warning": 70}
    resource = {"cpu_warning": 60, "disk_critical": 88}
    merged = merge_thresholds(resource, site)
    assert merged["cpu_warning"] == 60  # 资源 > 站点
    assert merged["cpu_critical"] == GLOBAL_DEFAULTS["cpu_critical"]  # 缺省回退
    assert merged["disk_critical"] == 88
    assert merged["memory_warning"] == GLOBAL_DEFAULTS["memory_warning"]
    # 未知键不混入
    assert "bogus" not in merge_thresholds({"bogus": 1})
