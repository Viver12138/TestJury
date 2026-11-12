"""PostgreSQL knowledge repository; publication uses compare-and-swap under a lock."""

from app.knowledge.contract import KnowledgeError
from app.knowledge.runtime import digest, verify_release
from app.storage.postgres import _PooledStorage


class PostgresKnowledgeStore(_PooledStorage):
    async def put(self, release: dict) -> None:
        verify_release(release)
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", release["version"])
            old = await conn.fetchval("SELECT payload FROM knowledge_builds WHERE version=$1", release["version"])
            if old is not None:
                if digest(old) != digest(release):
                    raise KnowledgeError("immutable build already exists with different content")
                return
            await conn.execute("INSERT INTO knowledge_builds(version,project_id,baseline,payload) VALUES($1,$2,$3,$4)",
                               release["version"], release["project_id"], release["baseline"]["type"], release)
            for chunk in release["chunks"]:
                if "vector" in chunk:
                    await conn.execute("INSERT INTO knowledge_vectors VALUES($1,$2,$3::vector)",
                                       release["version"], chunk["chunk_id"], str(chunk["vector"]))

    async def get(self, version: str) -> dict | None:
        pool = await self._get_pool()
        return await pool.fetchval("SELECT payload FROM knowledge_builds WHERE version=$1", version)

    async def current(self, project: str, baseline: str) -> dict | None:
        pool = await self._get_pool()
        return await pool.fetchval("""SELECT b.payload FROM knowledge_active a JOIN knowledge_builds b
            ON a.version=b.version WHERE a.project_id=$1 AND a.baseline=$2""", project, baseline)

    async def rank_vectors(self, version: str, chunk_ids: list[str], vector: list[float]) -> list[tuple[str, float]]:
        pool = await self._get_pool()
        rows = await pool.fetch("""SELECT chunk_id, 1-(embedding <=> $3::vector) AS similarity
            FROM knowledge_vectors WHERE version=$1 AND chunk_id=ANY($2::text[])
            ORDER BY embedding <=> $3::vector,chunk_id LIMIT 40""", version, chunk_ids, str(vector))
        return [(r["chunk_id"], r["similarity"]) for r in rows]

    async def activate(self, version: str, actor: str, reason: str, expected: str | None) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow("SELECT project_id,baseline FROM knowledge_builds WHERE version=$1", version)
            if row is None:
                raise KnowledgeError("unknown build")
            project, baseline = row["project_id"], row["baseline"]
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", project + ":" + baseline)
            previous = await conn.fetchval("SELECT version FROM knowledge_active WHERE project_id=$1 AND baseline=$2",
                                           project, baseline)
            if previous != expected:
                raise KnowledgeError("active version changed; refresh before publishing")
            await conn.execute("""INSERT INTO knowledge_active VALUES($1,$2,$3)
                ON CONFLICT(project_id,baseline) DO UPDATE SET version=EXCLUDED.version""", project, baseline, version)
            await conn.execute("""INSERT INTO knowledge_events(project_id,version,previous,actor,reason)
                VALUES($1,$2,$3,$4,$5)""", project, version, previous, actor, reason)

    async def history(self, project: str) -> list[dict]:
        pool = await self._get_pool()
        return [dict(r) for r in await pool.fetch(
            "SELECT * FROM knowledge_events WHERE project_id=$1 ORDER BY id", project)]
