"""Start a persistent local TestJury instance after non-destructive migrations."""
from __future__ import annotations

import asyncio
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import Settings
from app.main import create_app
from app.knowledge.postgres import PostgresKnowledgeStore
from app.knowledge.runtime import KnowledgeService
from app.core.versioning import compute_versions
from app.llm.factory import build_embedding_adapter
from app.llm.registry import ModelRegistry


async def initialize(release_path: Path, database_url: str):
    release = json.loads(release_path.read_text(encoding='utf-8'))
    acceptance = json.loads((ROOT / 'evidence/M2/acceptance' / (release['version'] + '.json')).read_text(encoding='utf-8'))
    store = PostgresKnowledgeStore(database_url)
    embedder = None
    try:
        await store.put(release)
        current = await store.current(release['project_id'], release['baseline']['type'])
        if current is None:
            profile = 'lexical-only'
            if release['profile'] != 'lexical-only':
                settings = Settings(database_url=database_url, knowledge_vector_enabled=True)
                embedder = build_embedding_adapter(ModelRegistry.load(settings.model_registry_path))
                profile = compute_versions(settings).embedding_profile
            await KnowledgeService(store, embedder=embedder, profile=profile).publish(release['version'], actor='codex-delegated-reviewer',
                reason='用户授权的本地技术预览；黄金集为代理标注，独立人工效果未验证', expected=None,
                acceptance=acceptance, allow_delegated=True)
        elif current['version'] != release['version']:
            print('已有启用版本，保持当前版本；新版本可通过受控接口切换。', flush=True)
    finally:
        if embedder is not None:
            await embedder.aclose()
        await store.close()


def main():
    import uvicorn
    database_url = os.environ.get('LOCAL_DATABASE_URL', 'postgresql://testjury:testjury@127.0.0.1:55432/testjury')
    environment = dict(os.environ, DATABASE_URL=database_url, PYTHONIOENCODING='utf-8')
    migration = subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], cwd=ROOT, env=environment)
    if migration.returncode:
        raise SystemExit(migration.returncode)
    release_path = Path(os.environ.get('LOCAL_KNOWLEDGE_RELEASE', str(ROOT / '.tmp/knowledge-vector-release-final.json')))
    release = json.loads(release_path.read_text(encoding='utf-8'))
    asyncio.run(initialize(release_path, database_url))
    credentials = ROOT / '.tmp/local-access.json'
    if credentials.exists():
        keys = json.loads(credentials.read_text(encoding='utf-8'))
    else:
        keys = [{'key': secrets.token_urlsafe(32), 'actor_id': 'local-reviewer', 'actor_type':'service',
                 'roles':['reviewer','kb_publisher']}]
        credentials.write_text(json.dumps(keys, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    settings = Settings(_env_file=ROOT / '.env', app_env='dev', database_url=database_url,
                        storage_backend='postgres', review_model_mode=os.environ.get('LOCAL_MODEL_MODE','live'),
                        review_topology=os.environ.get('LOCAL_TOPOLOGY','dual'), knowledge_enabled=True,
                        knowledge_vector_enabled=release['profile'] != 'lexical-only',
                        knowledge_delegated_acceptance=True, kb_context_top_k=4, kb_context_token_cap=4000,
                        bootstrap_api_keys=json.dumps(keys), run_worker=True)
    print('TestJury: http://127.0.0.1:8088 ; 访问凭证保存在 .tmp/local-access.json', flush=True)
    uvicorn.run(create_app(settings), host='127.0.0.1', port=8088, access_log=False)


if __name__ == '__main__':
    main()
