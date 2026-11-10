"""测试辅助：固定身份、请求体与配置（供 conftest 与用例共用）。"""

from __future__ import annotations

import json

from app.config import Settings

REVIEWER_KEY = "test-reviewer-key-0001"
REVIEWER2_KEY = "test-reviewer2-key-0002"
APPROVER_KEY = "test-approver-key-0003"
ADMIN_KEY = "test-admin-key-0004"
SERVICE_KEY = "test-service-key-0005"
REVOKED_KEY = "test-revoked-key-0006"
COMPAT_KEY = "test-compat-key-0007"


def bootstrap_keys() -> str:
    return json.dumps(
        [
            {"key": REVIEWER_KEY, "actor_id": "reviewer-1", "actor_type": "human", "roles": ["reviewer"]},
            {"key": REVIEWER2_KEY, "actor_id": "reviewer-2", "actor_type": "human", "roles": ["reviewer"]},
            {"key": APPROVER_KEY, "actor_id": "approver-1", "actor_type": "human", "roles": ["approver"]},
            {"key": ADMIN_KEY, "actor_id": "admin-1", "actor_type": "human", "roles": ["admin"]},
            {"key": SERVICE_KEY, "actor_id": "svc-1", "actor_type": "service", "roles": ["reviewer"]},
            {
                "key": COMPAT_KEY,
                "actor_id": "compat-caller",
                "actor_type": "service",
                "roles": ["reviewer"],
                "caller_id": "caller-compat",
            },
        ]
    )


def make_settings(**overrides: object) -> Settings:
    base = {
        "_env_file": None,
        "app_env": "test",
        "database_url": "postgresql+asyncpg://testjury:testjury@localhost:5432/testjury_test",
        "storage_backend": "memory",
        "run_worker": False,
        "bootstrap_api_keys": bootstrap_keys(),
        "decision_require_separation": True,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def auth_headers(key: str = REVIEWER_KEY) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def valid_case(case_id: str = "TC-DIG-0012", **overrides: object) -> dict:
    payload = {
        "case_id": case_id,
        "module": "挖宝",
        "test_type": "functional",
        "title": "洛阳挖宝 - 藏宝点发现与挖掘",
        "priority": "P1",
        "source": "manual",
        "preconditions": ["角色等级 ≥ 20", "背包至少 1 个空格"],
        "steps": [
            {"index": 1, "action": "点击【开始挖宝】按钮", "expected": "界面提示已生成藏宝点"},
            {"index": 2, "action": "传送到洛阳藏宝点坐标 (312, 480)", "expected": "角色到达藏宝点范围"},
            {"index": 3, "action": "点击【发现】按钮", "expected": "获得随机物品并进入背包"},
        ],
        "test_data": {"map": "洛阳"},
    }
    payload.update(overrides)
    return payload


def review_payload(case: dict | None = None, **overrides: object) -> dict:
    payload = {
        "case": case or valid_case(),
        "test_scope": {
            "feature_point": "藏宝点发现",
            "required_scenarios": ["正常发现", "背包已满"],
            "scope_version": "scope-test",
        },
        "automation_context": {
            "framework": "自研 UI 自动化框架",
            "state_query_capabilities": ["背包物品列表"],
        },
        "options": {"force": False},
    }
    payload.update(overrides)
    return payload
