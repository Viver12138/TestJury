"""Run paired, live dual-model reviews of a frozen authored case workbook.

Only knowledge availability changes. A disposable PostgreSQL database stores both
conditions; the local application's database and active knowledge are untouched.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import random
import re
import subprocess
import sys
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import asyncpg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import Settings
from app.core.auth import Principal
from app.core.enums import ActorType
from app.main import create_app
from app.services.excel_import import parse_workbook
from app.storage.models import BatchRecord, new_id
from app.storage.postgres import PostgresStorage


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + '\n',
                    encoding='utf-8', newline='\n')


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['live', 'mock'], required=True)
    parser.add_argument('--cases', type=Path, required=True, help='Frozen authored cases and separate annotations JSON')
    parser.add_argument('--release', type=Path)
    parser.add_argument('--concurrency', type=int, choices=[1, 2], default=2)
    args = parser.parse_args()
    args.cases = args.cases.resolve()
    args.release = (args.release or ROOT / ('.tmp/knowledge-vector-release-final.json' if args.mode == 'live'
                                           else '.tmp/knowledge-release.json')).resolve()
    dataset = json.loads(args.cases.read_text(encoding='utf-8'))
    workbook = ROOT / dataset['input_workbook']
    assert hashlib.sha256(workbook.read_bytes()).hexdigest() == dataset['input_sha256']
    cases = parse_workbook(workbook.read_bytes(), workbook.name)['cases']
    encoded = json.dumps(cases, ensure_ascii=False, sort_keys=True).encode()
    assert hashlib.sha256(encoded).hexdigest() == dataset['case_input_sha256']
    assert cases == dataset['cases'] and len(cases) == 10
    run_id = f"{args.mode}-{uuid.uuid4().hex[:10]}"
    directory = args.cases.parent / 'runs' / run_id
    directory.mkdir(parents=True, exist_ok=False)
    release = json.loads(args.release.read_text(encoding='utf-8'))
    proof = json.loads((ROOT / 'evidence/M2/acceptance' / (release['version'] + '.json')).read_text(encoding='utf-8'))
    base = os.environ.get('VERIFY_ADMIN_DATABASE_URL', 'postgresql://testjury:testjury@127.0.0.1:55432/testjury')
    dbname = 'testjury_compare_' + uuid.uuid4().hex[:12]
    assert re.fullmatch(r'testjury_compare_[0-9a-f]{12}', dbname)
    parts = urlsplit(base)
    dsn = urlunsplit((parts.scheme, parts.netloc, '/' + dbname, parts.query, parts.fragment))
    connection = await asyncpg.connect(base)
    await connection.execute(f'CREATE DATABASE "{dbname}"')
    write_json(directory/'setup.json', {'temporary_database':dbname,'mode':args.mode,'model_calls_started':False})
    migration = await asyncio.to_thread(subprocess.run,
        [sys.executable, '-m', 'alembic', 'upgrade', 'head'], cwd=ROOT,
        env=dict(os.environ, DATABASE_URL=dsn, PYTHONIOENCODING='utf-8'), capture_output=True,
        text=True, encoding='utf-8', errors='replace')
    if migration.returncode:
        raise RuntimeError('Comparison database migration failed; preserved for diagnosis: ' + dbname)
    common = dict(_env_file=ROOT / '.env', app_env='test', database_url=dsn, storage_backend='postgres',
                  run_worker=False, review_model_mode=args.mode, review_topology='dual',
                  knowledge_vector_enabled=release['profile'] != 'lexical-only',
                  kb_context_top_k=4, kb_context_token_cap=4000, bootstrap_api_keys='')
    storage = PostgresStorage(dsn)
    on_app = create_app(Settings(**common, knowledge_enabled=True), storage=storage, run_worker=False)
    off_app = create_app(Settings(**common, knowledge_enabled=False), storage=storage, run_worker=False)
    assert on_app.state.versions == off_app.state.versions
    for logger in ('httpcore', 'httpx', 'testjury.pipeline', 'testjury.http', 'testjury.worker'):
        logging.getLogger(logger).setLevel(logging.WARNING)
    service = on_app.state.knowledge
    await service.store.put(release)
    await service.publish(release['version'], actor='codex-delegated-reviewer', reason='isolated paired diagnostic',
                          expected=None, acceptance=proof, allow_delegated=True)
    source_hash = hashlib.sha256()
    for path in sorted((ROOT / 'app').rglob('*.py')):
        source_hash.update(path.relative_to(ROOT).as_posix().encode())
        source_hash.update(path.read_bytes())
    source_hash.update(Path(__file__).read_bytes())
    versions = on_app.state.versions.report_versions()
    source_hash.update(json.dumps(versions, sort_keys=True).encode())
    settings = on_app.state.settings
    config = {'review_tokens':settings.review_budget_tokens,'review_cost':settings.review_budget_cost,
              'batch_cost':settings.batch_budget_cost,'daily_cost':settings.daily_budget_cost,
              'job_timeout_seconds':settings.job_timeout_seconds,'blind_timeout_seconds':settings.stage_timeout_blind,
              'vote_timeout_seconds':settings.stage_timeout_vote,'arbitration_timeout_seconds':settings.stage_timeout_arbitration,
              'topology':'dual','roles':list(settings.review_roles),'models':versions['models'],
              'retrieval_top_k':4,'retrieval_token_cap':4000,'reranker_enabled':False,
              'comparison_concurrency':args.concurrency,'storage_backend':'postgres','random_seed':20261113}
    source_hash.update(json.dumps(config, sort_keys=True).encode())
    fingerprint = source_hash.hexdigest()
    batches = {condition:new_id() for condition in ('knowledge_on','knowledge_off')}
    for condition, batch_id in batches.items():
        await storage.create_batch(BatchRecord(id=batch_id, total=10, caller_id='paired-evaluator',
            input_hash=dataset['case_input_sha256'], idempotency_key=run_id + ':' + condition))
    principal = Principal('paired-evaluator', ActorType.SERVICE, frozenset({'reviewer'}), 'paired-evaluator')
    randomizer = random.Random(config['random_seed'])
    scheduled = []
    for case in cases:
        conditions = list(batches)
        randomizer.shuffle(conditions)
        for condition in conditions:
            # Ground-truth labels and experimental condition are never in the model's case data.
            payload = {'case':case, 'options':{'strict_kb':False},
                       'test_scope':{'feature_point':case['title'],'required_scenarios':[]},
                       'automation_context':{'framework':'API + 独立测试数据库',
                                              'state_query_capabilities':['HTTP JSON','数据库只读查询']}}
            app = on_app if condition == 'knowledge_on' else off_app
            submitted = await app.state.review_service.submit(payload, principal, batch_id=batches[condition])
            job = await storage.get_job(submitted.body['review_id'])
            assert (job.kb_build_version == release['version']) == (condition == 'knowledge_on')
            scheduled.append({'case_id':case['case_id'],'condition':condition,'review_id':job.id,
                              'case_sha256':hashlib.sha256(json.dumps(case,ensure_ascii=False,sort_keys=True).encode()).hexdigest()})
    manifest = {'run_id':run_id,'mode':args.mode,'created_at':datetime.now(timezone.utc).isoformat(),
       'dataset':args.cases.relative_to(ROOT).as_posix(),'dataset_sha256':hashlib.sha256(args.cases.read_bytes()).hexdigest(),
       'input_workbook_sha256':dataset['input_sha256'],'code_fingerprint':fingerprint,'config':config,
       'knowledge_on_version':release['version'],'knowledge_off_version':'kb-none',
       'temporary_database':dbname,'storage_database_disabled':False,'application_database_modified':False,
       'same_models_prompt_rubric_budget':True,'ground_truth_sent_to_models':False,'schedule':scheduled,
       'status':'running','temporary_database_removed':False}
    write_json(directory/'manifest.json',manifest)
    print(json.dumps({'run_id':run_id,'tasks':len(scheduled),'concurrency':args.concurrency,
                      'directory':directory.relative_to(ROOT).as_posix(),'config':config},ensure_ascii=False),flush=True)
    mapping = {item['review_id']:item for item in scheduled}
    completed = set()
    save_lock = asyncio.Lock()

    async def save_job(job):
        if not job.is_terminal:
            return
        async with save_lock:
            if job.id in completed:
                return
            item = mapping[job.id]
            runs = await storage.list_model_runs(job.id)
            ledger = await storage.list_model_budget(job.id)
            value = {**item,'job':asdict(job),'model_runs':[asdict(r) for r in runs],
                     'budget_ledger':ledger,'code_fingerprint':fingerprint}
            write_json(directory/item['condition']/(item['case_id']+'.json'),value)
            completed.add(job.id)
            report=job.report_json or {}
            coverage=report.get('appendix',{}).get('knowledge_review',{})
            print(json.dumps({'completed':len(completed),'case_id':job.case_id,'condition':item['condition'],
                              'status':job.status,'issues':len(report.get('issues',[])),
                              'knowledge_mode':coverage.get('mode'),'participation':report.get('review_completeness'),
                              'budget_exhausted':report.get('appendix',{}).get('budget',{}).get('exhausted')},ensure_ascii=False),flush=True)

    async def process():
        while len(completed)<len(scheduled):
            claimed = await on_app.state.worker.claim_next()
            if claimed is None:
                await asyncio.sleep(.5)
                continue
            # A common executor honors each task's frozen kb build; kb-none sends no knowledge.
            await on_app.state.worker.execute(claimed)
            await save_job(await storage.get_job(claimed.id))

    successful = False
    try:
        await asyncio.gather(*(process() for _ in range(args.concurrency)))
        successful = True
        manifest.update(status='completed',finished_at=datetime.now(timezone.utc).isoformat(),
                        terminal_tasks=len(completed),reports=sum(bool(json.loads(p.read_text(encoding='utf-8'))['job']['report_json'])
                            for condition in batches for p in (directory/condition).glob('*.json')))
    finally:
        for app in (on_app,off_app):
            close=getattr(app.state.review_model,'aclose',None)
            if close:await close()
        if service.embedder is not None:await service.embedder.aclose()
        await service.store.close()
        await storage.close()
        if successful:
            await connection.execute(f'DROP DATABASE "{dbname}" WITH (FORCE)')
            manifest['temporary_database_removed']=True
        else:
            manifest['status']='interrupted_database_preserved'
        await connection.close()
        write_json(directory/'manifest.json',manifest)
    print(json.dumps({'run_id':run_id,'status':manifest['status'],'reports':manifest.get('reports'),
                      'temporary_database_removed':manifest['temporary_database_removed']}),flush=True)


if __name__=='__main__':
    raise SystemExit(asyncio.run(main()))
