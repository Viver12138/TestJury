"""Measure local queue throughput using Mock models and a disposable database."""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import math
import os
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import asyncpg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

async def main():
    from app.config import Settings
    from app.core.auth import Principal
    from app.core.enums import ActorType
    from app.main import create_app

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jobs', type=int, default=50)
    parser.add_argument('--submit-concurrency', type=int, default=8)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--timeout', type=float, default=120)
    args = parser.parse_args()
    if min(args.jobs, args.submit_concurrency, args.workers, args.timeout) <= 0 or args.jobs > 500:
        parser.error('positive limits required; jobs must be <= 500')
    admin_dsn = os.environ.get('VERIFY_ADMIN_DATABASE_URL', 'postgresql://testjury:testjury@127.0.0.1:55432/testjury')
    name = 'testjury_benchmark_' + uuid.uuid4().hex[:12]
    admin = await asyncpg.connect(admin_dsn)
    await admin.execute(f'CREATE DATABASE "{name}"')
    parts = urlsplit(admin_dsn)
    dsn = urlunsplit((parts.scheme, parts.netloc, '/' + name, parts.query, parts.fragment))
    result = {'scope': 'local Mock service-layer queue benchmark, excludes HTTP/network, knowledge and providers',
              'temporary_database': name, 'application_database_modified': False,
              'jobs': args.jobs, 'submit_concurrency': args.submit_concurrency, 'workers': args.workers}
    output = ROOT / 'evidence/M2/queue_benchmark' / (name + '.json')
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        migration = await asyncio.create_subprocess_exec(sys.executable, '-m', 'alembic', 'upgrade', 'head',
            cwd=ROOT, env=dict(os.environ, DATABASE_URL=dsn, PYTHONIOENCODING='utf-8'),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        log, _ = await migration.communicate()
        if migration.returncode:
            raise RuntimeError('Disposable database migration failed: ' + log.decode(errors='replace'))
        settings = Settings(_env_file=None, app_env='test', storage_backend='postgres', database_url=dsn,
                            review_model_mode='mock', review_topology='dual', knowledge_enabled=False,
                            worker_concurrency=args.workers, max_queue_depth=1000, run_worker=False)
        app = create_app(settings, run_worker=False)
        principal = Principal('queue-benchmark', ActorType.SERVICE, frozenset({'reviewer'}), 'queue-benchmark')
        seed = json.loads((ROOT / 'datasets/minishop/v3/review.jsonl').read_text(encoding='utf-8').splitlines()[0])['case']
        timings = []
        submitted_ids = []
        limit = asyncio.Semaphore(args.submit_concurrency)
        async with app.router.lifespan_context(app):
            async def submit(index):
                async with limit:
                    case = copy.deepcopy(seed)
                    case['case_id'] = f'queue-benchmark-{index}'
                    started = time.perf_counter()
                    response = await app.state.review_service.submit({'case': case}, principal)
                    timings.append(time.perf_counter() - started)
                    submitted_ids.append(response.body['review_id'])

            start = time.perf_counter()
            await asyncio.wait_for(asyncio.gather(*(submit(i) for i in range(args.jobs))), args.timeout)
            submit_elapsed = time.perf_counter() - start
            app.state.worker.start()
            try:
                async def drain():
                    while True:
                        jobs = await app.state.storage.list_jobs(limit=args.jobs + 1)
                        if len(jobs) == args.jobs and all(j.is_terminal for j in jobs):
                            return jobs
                        await asyncio.sleep(0.05)
                jobs = await asyncio.wait_for(drain(), args.timeout)
            finally:
                await app.state.worker.stop()
            elapsed = time.perf_counter() - start
            statuses = {status: sum(j.status == status for j in jobs) for status in sorted({j.status for j in jobs})}
            passed = (len(set(submitted_ids)) == args.jobs and len(jobs) == args.jobs
                      and all(j.status == 'done' and j.report_json and j.attempt_count == 1 for j in jobs))
            result.update(passed=passed, statuses=statuses, unique_jobs=len(set(submitted_ids)),
                          submit_seconds=round(submit_elapsed, 3), total_seconds=round(elapsed, 3),
                          submit_p95_ms=round(sorted(timings)[math.ceil(len(timings) * .95) - 1] * 1000, 2),
                          completed_jobs_per_second=round(args.jobs / elapsed, 2),
                          all_jobs_single_attempt=all(j.attempt_count == 1 for j in jobs))
    finally:
        try:
            await admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
            result['temporary_database_removed'] = True
        finally:
            await admin.close()
            output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(result))
    return 0 if result.get('passed') else 1


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
