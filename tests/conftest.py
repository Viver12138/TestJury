"""共享测试夹具：仓库路径、工作目录、内存应用、客户端与 PostgreSQL 迁移。"""

from __future__ import annotations

import asyncio
import shutil
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.main import create_app
from app.rubric.loader import RubricRepository
from app.schemas.report import REPORT_SCHEMA_VERSION
from tests.helpers import (  # noqa: F401 - 供用例直接使用
    ADMIN_KEY,
    APPROVER_KEY,
    REVIEWER2_KEY,
    REVIEWER_KEY,
    REVOKED_KEY,
    SERVICE_KEY,
    auth_headers,
    make_settings,
    review_payload,
    valid_case,
)
from tests.pg import available, dsn, reset_schema, run_alembic

REPO_ROOT = Path(__file__).resolve().parents[1]
WORK_ROOT = REPO_ROOT / ".testwork"


@pytest.fixture()
def workdir() -> Iterator[Path]:
    WORK_ROOT.mkdir(exist_ok=True)
    path = WORK_ROOT / uuid.uuid4().hex[:12]
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


_COPY_ITEMS = ("docs", "design", "rubric", "schemas", "scripts", "evidence", ".github", "README.md")


@pytest.fixture()
def repo_copy():
    """把契约检查所需的仓库子集复制到工作目录（不复制 .venv/.git/临时目录）。"""

    def _copy(destination: Path) -> Path:
        destination.mkdir(parents=True, exist_ok=True)
        for name in _COPY_ITEMS:
            source = REPO_ROOT / name
            if source.is_dir():
                shutil.copytree(
                    source,
                    destination / name,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
                )
            elif source.is_file():
                shutil.copy2(source, destination / name)
        return destination

    return _copy


@pytest.fixture()
def settings() -> Settings:
    return make_settings()


@pytest.fixture()
def app(settings: Settings):
    return create_app(settings, run_worker=False)


@pytest.fixture()
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        yield test_client


@asynccontextmanager
async def _async_client(app) -> AsyncIterator[httpx.AsyncClient]:
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as async_client:
            yield async_client


@pytest.fixture()
async def async_client(app) -> AsyncIterator[httpx.AsyncClient]:
    async with _async_client(app) as client:
        yield client


@pytest.fixture()
def rubric_repository(repo_root: Path) -> RubricRepository:
    return RubricRepository(
        rubric_path=repo_root / "rubric" / "rubric.yaml",
        schema_path=repo_root / "rubric" / "schema.json",
    )


@pytest.fixture(scope="session")
def report_schema_version() -> str:
    return REPORT_SCHEMA_VERSION


# ── PostgreSQL（迁移 / fencing / mock-e2e） ──


@pytest.fixture(scope="session")
def postgres_dsn() -> str:
    if not available():
        pytest.skip(
            "PostgreSQL 不可用；请先执行 "
            "docker compose -f deploy/docker-compose.yml up -d postgres"
        )
    return dsn()


@pytest.fixture()
def clean_database(postgres_dsn: str) -> str:
    asyncio.run(reset_schema())
    return postgres_dsn


@pytest.fixture()
def migrated_database(clean_database: str) -> str:
    result = run_alembic("upgrade", "head")
    assert result.returncode == 0, result.stdout + result.stderr
    return clean_database
