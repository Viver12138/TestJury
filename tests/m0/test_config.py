"""ACC-M0-002：配置缺失时快速失败，不监听端口、不泄露密钥。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]


def _clean_env() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key.upper() != "DATABASE_URL"}
    env["PYTHONPATH"] = str(REPO_ROOT)
    env["PYTHONIOENCODING"] = "utf-8"
    env["APP_ENV"] = "test"
    env["STORAGE_BACKEND"] = "memory"
    env.pop("BOOTSTRAP_API_KEYS", None)
    return env


def test_missing_database_url_exits_nonzero() -> None:
    process = subprocess.run(
        [sys.executable, "-m", "app.bootstrap"],
        cwd=REPO_ROOT,
        env=_clean_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    output = process.stdout + process.stderr
    assert process.returncode != 0, output
    assert "DATABASE_URL" in output, output
    assert "Uvicorn running" not in output, output


def test_settings_rejects_empty_database_url() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="test",
            database_url="",
            storage_backend="memory",
        )


def test_production_rejects_memory_storage() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="prod",
            database_url="postgresql+asyncpg://user:pass@localhost/db",
            storage_backend="memory",
        )


def test_production_rejects_bootstrap_keys() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="prod",
            database_url="postgresql+asyncpg://user:pass@localhost/db",
            storage_backend="postgres",
            bootstrap_api_keys='[{"key":"dev-key-123","actor_id":"x"}]',
        )


def test_error_message_does_not_echo_secret() -> None:
    process = subprocess.run(
        [sys.executable, "-m", "app.bootstrap"],
        cwd=REPO_ROOT,
        env=_clean_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    output = process.stdout + process.stderr
    assert "postgresql+asyncpg://" not in output, output
