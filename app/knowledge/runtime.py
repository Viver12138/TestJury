"""Immutable knowledge releases, scoped retrieval and reproducible evidence packs.

Publishing is a separate operation from approving source documents. Retrieval always
uses the build frozen on the job, never the current active pointer.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import math
import re
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from app.knowledge.contract import KnowledgeError
from app.llm.base import AdapterError, EmbeddingAdapter, RerankAdapter

RETRIEVER_VERSION = "hybrid-bm25-rrf-4"


def _endpoints(text: str) -> list[tuple[str, str]]:
    return re.findall(r"\b(GET|POST|PUT|PATCH|DELETE)\s+(/api/[\w/{}.\-]+)", text, re.IGNORECASE)


def _matches_endpoint(template: tuple[str, str], request: tuple[str, str]) -> bool:
    method, path = template
    pattern = re.sub(r"\\\{[^{}]+\\\}", r"[^/]+", re.escape(path))
    return method.upper() == request[0].upper() and re.fullmatch(pattern, request[1]) is not None


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def tokens(text: str) -> list[str]:
    text = text.casefold()
    words = re.findall(r"[a-z0-9_./:-]+", text)
    for run in re.findall(r"[\u3400-\u9fff]+", text):
        words.extend(run[i:i + 2] for i in range(max(1, len(run) - 1)))
    return words


def validate_candidate(candidate: dict[str, Any]) -> None:
    if candidate.get("status") != "candidate" or candidate.get("publication_status") != "unpublished":
        raise KnowledgeError("only an unpublished candidate can be indexed")
    if not candidate.get("chunks") or not candidate.get("review_baseline"):
        raise KnowledgeError("candidate must contain chunks and an explicit baseline")
    ids: set[str] = set()
    for chunk in candidate["chunks"]:
        if chunk["chunk_id"] in ids:
            raise KnowledgeError("duplicate chunk")
        ids.add(chunk["chunk_id"])
        if chunk["project_id"] != candidate["project_id"] or chunk["kb_build_version"] != candidate["kb_build_version"]:
            raise KnowledgeError("chunk scope/version mismatch")
        if chunk["rule_status"] != "reviewed" or not chunk.get("source_evidence"):
            raise KnowledgeError("unreviewed or unsourced chunk")
        if hashlib.sha256(chunk["text"].encode()).hexdigest() != chunk["content_hash"]:
            raise KnowledgeError("chunk content hash mismatch")


def validate_vectors(vectors: list[list[float]], count: int, dimension: int = 1024) -> None:
    if len(vectors) != count:
        raise KnowledgeError("embedding count mismatch")
    for vector in vectors:
        if len(vector) != dimension or any(not math.isfinite(x) for x in vector) or not any(vector):
            raise KnowledgeError("invalid embedding dimension/value")


class MemoryKnowledgeStore:
    def __init__(self) -> None:
        self.builds: dict[str, dict] = {}
        self.active: dict[tuple[str, str], str] = {}
        self.events: list[dict] = []
        self.lock = asyncio.Lock()

    async def put(self, release: dict) -> None:
        verify_release(release)
        async with self.lock:
            key = release["version"]
            old = self.builds.get(key)
            if old is not None and digest(old) != digest(release):
                raise KnowledgeError("immutable build already exists with different content")
            self.builds[key] = copy.deepcopy(release)

    async def get(self, version: str) -> dict | None:
        return copy.deepcopy(self.builds.get(version))

    async def current(self, project: str, baseline: str) -> dict | None:
        return await self.get(self.active.get((project, baseline), ""))

    async def activate(self, version: str, actor: str, reason: str, expected: str | None) -> None:
        async with self.lock:
            release = self.builds[version]
            key = (release["project_id"], release["baseline"]["type"])
            if self.active.get(key) != expected:
                raise KnowledgeError("active version changed; refresh before publishing")
            self.active[key] = version
            self.events.append({"version": version, "previous": expected, "actor": actor, "reason": reason})

    async def history(self, project: str) -> list[dict]:
        return copy.deepcopy([e for e in self.events if self.builds[e["version"]]["project_id"] == project])


async def index_candidate(candidate: dict, *, embedder: EmbeddingAdapter | None = None,
                          profile: str = "lexical-only") -> dict:
    validate_candidate(candidate)
    chunks = copy.deepcopy(candidate["chunks"])
    if embedder is not None:
        if profile == "lexical-only":
            raise KnowledgeError("embedding requires a named immutable profile")
        for start in range(0, len(chunks), 16):
            batch = chunks[start:start + 16]
            response = await embedder.embed([c["heading_path"] + "\n" + c["text"] for c in batch])
            validate_vectors(response.vectors, len(batch))
            for chunk, vector in zip(batch, response.vectors, strict=True):
                chunk["vector"] = vector
    elif profile != "lexical-only":
        raise KnowledgeError("missing embedding adapter")
    payload = {
        "project_id": candidate["project_id"], "baseline": candidate["review_baseline"],
        "content_version": candidate["kb_content_version"], "candidate_version": candidate["kb_build_version"],
        "profile": profile, "retriever": RETRIEVER_VERSION, "chunks": chunks,
        "retriever_fingerprint": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "excluded_documents": candidate["excluded_documents"],
        "limitations": candidate.get("release_blockers", []),
    }
    return {**payload, "version": "kb-runtime-" + digest(payload)}


def verify_release(release: dict) -> None:
    payload = {k: v for k, v in release.items() if k != "version"}
    if release.get("version") != "kb-runtime-" + digest(payload):
        raise KnowledgeError("runtime release integrity check failed")


def _cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True)) / (
        math.sqrt(sum(x * x for x in left)) * math.sqrt(sum(x * x for x in right))
    )


class KnowledgeService:
    def __init__(self, store: Any, *, embedder: EmbeddingAdapter | None = None,
                 reranker: RerankAdapter | None = None, profile: str = "lexical-only") -> None:
        self.store = store
        self.embedder = embedder
        self.reranker = reranker
        self.profile = profile

    async def resolve(self, project: str, baseline: str, module: str) -> dict | None:
        release = await self.store.current(project, baseline)
        if release:
            verify_release(release)
            if any(c["module"] == module for c in release["chunks"]):
                return release
        return None

    async def publish(self, version: str, *, actor: str, reason: str, expected: str | None,
                      acceptance: dict, allow_delegated: bool = False) -> None:
        release = await self.store.get(version)
        if release is None:
            raise KnowledgeError("unknown build")
        verify_release(release)
        if release["retriever"] != RETRIEVER_VERSION:
            raise KnowledgeError("retrieval implementation unavailable; rebuild before publishing")
        if release["profile"] != "lexical-only" and (self.embedder is None or release["profile"] != self.profile):
            raise KnowledgeError("embedding profile unavailable; configure it before publishing")
        if not reason.strip() or not actor.strip():
            raise KnowledgeError("publication requires actor and reason")
        if acceptance.get("build_version") != version or acceptance.get("passed") is not True:
            raise KnowledgeError("acceptance must pass for this exact build")
        if acceptance.get("annotation_type") != "independent_human" and not allow_delegated:
            raise KnowledgeError("delegated acceptance is not enabled")
        if not acceptance.get("dataset_sha256") or not acceptance.get("review_record_sha256"):
            raise KnowledgeError("acceptance must bind dataset and review record")
        await self.store.activate(version, actor, reason, expected)

    async def retrieve(self, version: str, *, project: str, module: str, query: str,
                       product_version: str, platform: str = "all", top_k: int = 10,
                       char_cap: int = 30000, as_of: str | None = None) -> dict:
        release = await self.store.get(version)
        if release is None:
            raise KnowledgeError("frozen knowledge version is unavailable")
        verify_release(release)
        if release["project_id"] != project or release["baseline"]["product_version"] != product_version:
            raise KnowledgeError("knowledge project/product mismatch")
        if release["retriever"] != RETRIEVER_VERSION:
            raise KnowledgeError("frozen retrieval implementation unavailable; rebuild before switching")
        day = as_of or date.today().isoformat()
        chunks = [c for c in release["chunks"] if c["module"] in (module, None)
                  and product_version in c["product_version"]
                  and ("all" in c["platforms"] or platform in c["platforms"])
                  and (not c.get("effective_from") or c["effective_from"] <= day)
                  and (not c.get("effective_until") or c["effective_until"] >= day)]
        if not any(c["module"] == module for c in chunks):
            chunks = []
        query_tokens = Counter(tokens(query))
        keyword: list[tuple[int, float]] = []
        corpus = [Counter(tokens(c["heading_path"] + " " + c["text"])) for c in chunks]
        frequency = Counter(t for body in corpus for t in body)
        average_length = sum(sum(c.values()) for c in corpus) / max(1, len(corpus))
        for i, (chunk, body) in enumerate(zip(chunks, corpus, strict=True)):
            title = set(tokens(chunk["heading_path"]))
            score = 0.0
            for term in query_tokens:
                tf = body[term]
                if not tf:
                    continue
                idf = math.log(1 + (len(corpus) - frequency[term] + 0.5) / (frequency[term] + 0.5))
                norm = 1.2 * (0.75 + 0.25 * sum(body.values()) / max(1, average_length))
                score += idf * (tf * 2.2 / (tf + norm)) * (2 if term in title else 1)
            if chunk["doc_id"].casefold() in query.casefold():
                score += 10
            if score > 0:
                keyword.append((i, score))
        keyword.sort(key=lambda x: (-x[1], chunks[x[0]]["chunk_id"]))
        channels: dict[int, list[str]] = {}
        scores: dict[int, float] = {}
        warnings = []
        rankings = [("keyword", keyword[:40])]
        if release["profile"] != "lexical-only" and chunks:
            if self.embedder is None or release["profile"] != self.profile:
                warnings.append("embedding_profile_unavailable")
            else:
                try:
                    response = await self.embedder.embed([query])
                    validate_vectors(response.vectors, 1)
                    if hasattr(self.store, "rank_vectors"):
                        positions = {c["chunk_id"]: i for i, c in enumerate(chunks)}
                        hits = await self.store.rank_vectors(version, list(positions), response.vectors[0])
                        vector = [(positions[key], score) for key, score in hits]
                    else:
                        vector = [(i, _cosine(response.vectors[0], c["vector"])) for i, c in enumerate(chunks)]
                    vector.sort(key=lambda x: (-x[1], chunks[x[0]]["chunk_id"]))
                    # A nearest neighbour always exists; low similarity alone is not evidence.
                    if not keyword:
                        vector = [entry for entry in vector if entry[1] >= 0.45]
                    rankings.append(("vector", vector[:40]))
                except (AdapterError, TimeoutError):
                    warnings.append("embedding_failed")
        for channel, ranking in rankings:
            for rank, (i, _) in enumerate(ranking, 1):
                scores[i] = scores.get(i, 0) + 1 / (60 + rank)
                channels.setdefault(i, []).append(channel)
        ordered = sorted(scores, key=lambda i: (-scores[i], chunks[i]["chunk_id"]))[:40]
        rerank_scores: dict[int, float] = {}
        if self.reranker is not None and ordered:
            try:
                result = await self.reranker.rerank(query, [chunks[i]["text"] for i in ordered], top_n=len(ordered))
                hits = result.hits
                if (len({h.index for h in hits}) != len(hits)
                        or any(h.index < 0 or h.index >= len(ordered) or not math.isfinite(h.score) for h in hits)):
                    raise KnowledgeError("invalid reranker result")
                rerank_scores = {ordered[h.index]: h.score for h in hits}
                ordered.sort(key=lambda i: (-rerank_scores.get(i, -math.inf), -scores[i]))
            except (AdapterError, TimeoutError, KnowledgeError):
                warnings.append("rerank_failed")
        # Preserve explicit API contracts alongside semantic rules, even when the
        # general ranking prefers long business-rule chunks. A method mismatch
        # must never introduce an unrelated create/update contract.
        requests = set(_endpoints(query))
        endpoints = {i: set(_endpoints(c["heading_path"] + "\n" + c["text"]))
                     for i, c in enumerate(chunks)}
        coverage = {i: {r for r in requests if any(_matches_endpoint(t, r) for t in paths)}
                    for i, paths in endpoints.items()}
        priority: list[int] = []
        for kind, channel in (("INTERFACE", "interface_contract"), ("REQUIREMENT", "endpoint_behavior")):
            covered: set[tuple[str, str]] = set()
            candidates = [i for i, c in enumerate(chunks) if c["knowledge_type"] == kind and coverage[i]]
            # Prefer a focused contract over example data mentioning several APIs.
            # Requirements carry behavior which a short method/path chunk omits.
            candidates.sort(key=lambda i: (len(endpoints[i]) - len(coverage[i]),
                                            -scores.get(i, 0) if kind == "REQUIREMENT" else 0,
                                            len(chunks[i]["text"]), chunks[i]["chunk_id"]))
            for i in candidates:
                if len(priority) >= max(0, top_k - 1):
                    break
                if not coverage[i] - covered or any(chunks[j]["doc_id"] == chunks[i]["doc_id"] for j in priority):
                    continue
                if sum(len(chunks[j]["text"]) for j in priority) + len(chunks[i]["text"]) > char_cap:
                    continue
                priority.append(i)
                covered.update(coverage[i])
                channels.setdefault(i, []).append(channel)
                scores.setdefault(i, 0.0)
        ordered = priority + [i for i in ordered if i not in priority]
        evidence = []
        used = 0
        per_document: Counter = Counter()
        for i in ordered:
            chunk = chunks[i]
            if per_document[chunk["doc_id"]] >= 1:
                continue
            if used + len(chunk["text"]) > char_cap:
                continue  # never truncate a rule/table in the middle
            evidence.append({k: copy.deepcopy(v) for k, v in chunk.items() if k != "vector"})
            evidence[-1].update({"retrieval_channels": channels[i], "rrf_score": scores[i],
                                 "rerank_score": rerank_scores.get(i), "runtime_version": version})
            used += len(chunk["text"])
            per_document[chunk["doc_id"]] += 1
            if len(evidence) >= top_k:
                break
        pack = {"build_version": version, "content_version": release["content_version"],
                "retriever_version": RETRIEVER_VERSION,
                "project_id": project, "module": module, "baseline": release["baseline"],
                "as_of": day, "query": query, "evidence": evidence, "warnings": warnings,
                "profile": release["profile"], "limitations": release["limitations"]}
        pack["pack_hash"] = digest(pack)
        return pack
