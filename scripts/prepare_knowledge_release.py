"""Build and evaluate a candidate; writes reviewable artifacts, does not activate it."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.knowledge.build import build_candidate
from app.knowledge.evaluation import evaluate_retrieval
from app.knowledge.runtime import KnowledgeService, MemoryKnowledgeStore, index_candidate


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', required=True, choices=['current_implementation', 'target_specification'])
    parser.add_argument('--dataset', type=Path, default=ROOT / 'datasets/minishop/v3')
    parser.add_argument('--output', type=Path, default=ROOT / '.tmp/knowledge-release.json')
    parser.add_argument('--vector', action='store_true')
    parser.add_argument('--reuse-vectors', type=Path)
    args = parser.parse_args()
    candidate = build_candidate(ROOT, baseline_type=args.baseline)
    embedder = None
    profile = 'lexical-only'
    if args.vector:
        from dotenv import load_dotenv
        from app.config import Settings
        from app.core.versioning import compute_versions
        from app.llm.registry import ModelRegistry
        from app.llm.factory import build_embedding_adapter
        load_dotenv(ROOT / '.env')
        settings = Settings(database_url='postgresql://unused/unused_test')
        embedder = build_embedding_adapter(ModelRegistry.load(settings.model_registry_path))
        profile = compute_versions(settings).embedding_profile
    try:
        if args.reuse_vectors:
            from app.knowledge.runtime import digest, verify_release
            previous = json.loads(args.reuse_vectors.read_text(encoding='utf-8'))
            verify_release(previous)
            if previous['profile'] != profile or profile == 'lexical-only':
                raise ValueError('cached vector profile must match current embedding profile')
            cached = {(c['heading_path'], c['content_hash']): c['vector'] for c in previous['chunks']}
            release = await index_candidate(candidate)
            for chunk in release['chunks']:
                key = (chunk['heading_path'], chunk['content_hash'])
                if key in cached:
                    chunk['vector'] = cached[key]
                else:
                    from app.knowledge.runtime import validate_vectors
                    response = await embedder.embed([chunk['heading_path'] + '\n' + chunk['text']])
                    validate_vectors(response.vectors, 1)
                    chunk['vector'] = response.vectors[0]
            release['profile'] = profile
            release['version'] = 'kb-runtime-' + digest({k:v for k,v in release.items() if k != 'version'})
        else:
            release = await index_candidate(candidate, embedder=embedder, profile=profile)
        service = KnowledgeService(MemoryKnowledgeStore(), embedder=embedder, profile=profile)
        await service.store.put(release)
        evaluation = await evaluate_retrieval(service, release['version'], args.dataset)
    finally:
        if embedder is not None:
            await embedder.aclose()
    review_path = ROOT / 'evidence/M2/delegated_content_review.json'
    evaluation['review_record_sha256'] = hashlib.sha256(review_path.read_bytes()).hexdigest()
    evaluation['release_scope'] = 'delegated_technical_preview'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(release, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    proof = ROOT / 'evidence/M2/acceptance' / (release['version'] + '.json')
    proof.parent.mkdir(parents=True, exist_ok=True)
    proof.write_text(json.dumps(evaluation, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'version': release['version'], 'documents': candidate['documents'],
                      'chunks': len(release['chunks']), 'metrics': evaluation['metrics'],
                      'passed': evaluation['passed'], 'activation': 'not_performed'}, ensure_ascii=False))
    return 0 if evaluation['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
