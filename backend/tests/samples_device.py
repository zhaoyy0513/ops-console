"""现场真实设备接口响应样本（2026-09-21 抓包截取）——映射层回归测试。

robotCode/robotName 等为上游接口线上字段名（wire contract），保持原样。
"""

# 环境 50: GET /mission/robot/info/active  信封 records
ENV50_BODY = {
    "code": "SUCCESS",
    "desc": "SUCCESS",
    "records": [
        {"id": 123, "robotCode": "asrs23", "robotName": "RB-23", "robotType": "rack",
         "x": 22, "y": 65, "battery": 82, "mode": 2, "status": 1, "robotStatus": -1,
         "ipAddress": "10.28.222.23", "createDate": 1762511330006},
        {"id": 124, "robotCode": "asrs24", "robotName": "RB-24", "x": 104, "y": 32,
         "battery": 82, "status": 1, "createDate": 1690377773244},
    ],
}

# 环境 12: GET /mission/agent/list  信封 result + online 字段
ENV12_BODY = {
    "status": 200,
    "result": [
        {"id": 4769, "robotName": "SIM-001", "robotCode": "sim001", "robotType": "mobile",
         "x": 33, "y": 37, "battery": 57, "status": 0, "runtimeStatus": 2, "online": 1,
         "errorCode": None, "createDate": 1788523158784, "physicalAddress": "sim001"},
        {"id": 4771, "robotName": "SIM-002", "robotCode": "sim002", "x": 45, "y": 31,
         "battery": 58, "status": 0, "runtimeStatus": 4, "online": 0, "errorCode": "E102",
         "createDate": 1788523158799},
    ],
}
