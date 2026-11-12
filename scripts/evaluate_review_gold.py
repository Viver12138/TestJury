"""Execute live or mock reviews against authored gold; never present mock as quality evidence."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import Settings
from app.core.auth import Principal
from app.core.enums import ActorType
from app.knowledge.evaluation import load_dataset
from app.main import create_app


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['live', 'mock'], required=True)
    parser.add_argument('--split', choices=['dev', 'validation', 'frozen', 'regression', 'all'], default='dev')
    parser.add_argument('--limit', type=int, default=6)
    parser.add_argument('--topology', choices=['single', 'dual', 'multi'], default='dual')
    parser.add_argument('--release', type=Path)
    parser.add_argument('--dataset', type=Path, default=ROOT / 'datasets/minishop/v3')
    parser.add_argument('--case-id', action='append', help='Evaluate only named cases; repeat to select several')
    parser.add_argument('--budget-tokens', type=int, help='Evaluation token reservation limit; cost limit is unchanged')
    args = parser.parse_args()
    if args.release is None:
        args.release = ROOT / ('.tmp/knowledge-vector-release-final.json' if args.mode == 'live'
                               else '.tmp/knowledge-release.json')
    release = json.loads(args.release.read_text(encoding='utf-8'))
    overrides = {'review_budget_tokens': args.budget_tokens} if args.budget_tokens is not None else {}
    settings = Settings(_env_file=ROOT / '.env', app_env='test', storage_backend='memory',
                        database_url='postgresql://unused/unused_test', run_worker=False,
                        review_model_mode=args.mode, knowledge_enabled=True, review_topology=args.topology,
                        knowledge_vector_enabled=release['profile'] != 'lexical-only',
                        kb_context_top_k=4, kb_context_token_cap=4000, **overrides)
    budget_config = {'review_tokens': settings.review_budget_tokens, 'review_cost': settings.review_budget_cost,
                     'batch_cost': settings.batch_budget_cost, 'daily_cost': settings.daily_budget_cost}
    app = create_app(settings, run_worker=False)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    source_hash = hashlib.sha256()
    for path in sorted((ROOT / 'app').rglob('*.py')):
        source_hash.update(path.relative_to(ROOT).as_posix().encode())
        source_hash.update(path.read_bytes())
    source_hash.update(json.dumps(app.state.versions.report_versions(), sort_keys=True).encode())
    source_hash.update(Path(__file__).read_bytes())
    source_hash.update(json.dumps(budget_config, sort_keys=True).encode())
    code_fingerprint = source_hash.hexdigest()
    await app.state.knowledge.store.put(release)
    proof_path = ROOT / 'evidence/M2/acceptance' / (release['version'] + '.json')
    proof = json.loads(proof_path.read_text(encoding='utf-8'))
    await app.state.knowledge.publish(release['version'], actor='codex-delegated-reviewer',
                                      reason='isolated evaluation only', expected=None,
                                      acceptance=proof, allow_delegated=True)
    manifest, data = load_dataset(args.dataset)
    if args.case_id and set(args.case_id) - {x['id'] for x in data['review.jsonl']}:
        parser.error('unknown case id')
    selected = [x for x in data['review.jsonl'] if args.split == 'all' or x['split'] == args.split][:args.limit]
    if args.case_id:
        selected = [x for x in data['review.jsonl'] if x['id'] in args.case_id]
    directory = ROOT / 'evidence/M2' / ('review_eval_' + args.mode) / manifest['version'] / (args.topology + '-' + code_fingerprint[:12])
    directory.mkdir(parents=True, exist_ok=True)
    principal = Principal('gold-evaluator', ActorType.SERVICE, frozenset({'reviewer'}), 'gold-evaluator')
    results = []
    try:
        for item in selected:
            path = directory / (item['id'] + '.json')
            if path.exists():
                saved = json.loads(path.read_text(encoding='utf-8'))
                if saved.get('build_version') == release['version'] and saved.get('code_fingerprint') == code_fingerprint:
                    results.append(saved)
                    continue
            print('Evaluating ' + item['id'], flush=True)
            payload = {'case': item['case'], 'options': {'strict_kb': True},
                       'test_scope': {'feature_point': item['case']['title'], 'required_scenarios': []},
                       'automation_context': {'framework': 'API + 独立数据库',
                                              'state_query_capabilities': ['HTTP JSON', '数据库只读查询']}}
            submitted = await app.state.review_service.submit(payload, principal)
            status = await app.state.worker.run_once()
            job = await app.state.storage.get_job(submitted.body['review_id'])
            report = job.report_json
            findings = (report or {}).get('issues', [])
            expected = item['expected_findings']
            # Category-level matching is a conservative diagnostic, not independent semantic grading.
            matches = sum(any(f.get('dimension') == e['dimension'] and f.get('step_index') == e['step_index']
                              and f.get('category') in {e['category'], '状态不自洽', '预期不明确'} for f in findings)
                          for e in expected)
            result = {'id': item['id'], 'mode': args.mode, 'split': item['split'], 'build_version': release['version'],
                      'code_fingerprint': code_fingerprint,
                      'evaluation_budget': budget_config,
                      'dataset_version': manifest['version'], 'dataset_files': manifest['files'],
                      'annotation_type': manifest['annotation_type'], 'status': status, 'error': job.last_error,
                      'expected_count': len(expected), 'reported_count': len(findings), 'matched_count': matches,
                      'report': report}
            runs = await app.state.storage.list_model_runs(job.id)
            result['model_errors'] = [{'role':r.role, 'operation':r.operation, 'error':r.error}
                                      for r in runs if r.status == 'error']
            path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str) + '\n',
                            encoding='utf-8', newline='\n')
            results.append(result)
            print(json.dumps({k: v for k, v in result.items() if k != 'report'}, ensure_ascii=False), flush=True)
    finally:
        close = getattr(app.state.review_model, 'aclose', None)
        if close:
            await close()
        if app.state.knowledge.embedder is not None:
            await app.state.knowledge.embedder.aclose()
    expected = sum(x['expected_count'] for x in results)
    detected = sum(x['matched_count'] for x in results)
    expected_participation = f'{len(settings.review_roles)}/{len(settings.review_roles)}'
    def fully_assessed(item):
        completeness = (item.get('report') or {}).get('review_completeness', {})
        return (completeness.get('complete') is True and completeness.get('blind') == expected_participation
                and completeness.get('vote') == expected_participation)

    summary = {'mode': args.mode, 'build_version': release['version'], 'cases': len(results),
               'dataset_version': manifest['version'], 'code_fingerprint': code_fingerprint,
               'reports': sum(bool(x['report']) for x in results),
               'expected_issues': expected, 'matched_issues': detected,
               'diagnostic_recall': detected / expected if expected else None,
               'clean_cases': sum(x['expected_count'] == 0 for x in results),
               'clean_cases_with_reported_issues': sum(x['expected_count'] == 0 and x['reported_count'] > 0 for x in results),
               'reported_issues': sum(x['reported_count'] for x in results),
               'topology': args.topology, 'evaluation_budget': budget_config,
               'fully_assessed_cases': sum(fully_assessed(x) for x in results),
               'budget_exhausted_cases': sum(bool((x.get('report') or {}).get('appendix', {}).get('budget', {})
                                                   .get('exhausted')) for x in results),
               'independent_human_validation': False,
               'limitations': ['category-level diagnostic matching', 'authored seed set, not blind independent gold',
                               'mock runs verify plumbing only']}
    (directory / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n',
                                          encoding='utf-8', newline='\n')
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 0 if summary['reports'] == len(results) else 1


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
