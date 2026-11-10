"""ACC-M0-016：CI 聚合门禁在无真实模型环境下可用（契约检查 + 应用启动）。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from tests.helpers import make_settings

REPO_ROOT = Path(__file__).resolve().parents[2]
MODEL_KEY_ENVS = ("QWEN_API_KEY", "DEEPSEEK_API_KEY", "KIMI_API_KEY")


def _clean_env() -> dict[str, str]:
    env = dict(os.environ)
    for name in MODEL_KEY_ENVS:
        env.pop(name, None)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def test_contract_checks_pass_without_model_keys() -> None:
    process = subprocess.run(
        [sys.executable, "scripts/check_contracts.py"],
        cwd=REPO_ROOT,
        env=_clean_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
    )
    output = process.stdout + process.stderr
    assert process.returncode == 0, output
    assert "通过" in output


def test_app_starts_with_mock_configuration_without_model_keys() -> None:
    app = create_app(make_settings(), run_worker=False)
    with TestClient(app) as client:
        assert client.get("/livez").status_code == 200
        assert client.get("/readyz").status_code == 200


def test_no_real_model_calls_in_tests() -> None:
    source = (REPO_ROOT / "app" / "pipeline" / "orchestrator.py").read_text(encoding="utf-8")
    assert "MockChatClient" in source
    for name in MODEL_KEY_ENVS:
        assert name not in source
