"""从 `report_json` 重建 `issues` 投影，并校验一致性。

用法：
    python scripts/rebuild_projection.py --all            # 重建所有有报告的评审
    python scripts/rebuild_projection.py --review <id>    # 重建单条
    python scripts/rebuild_projection.py --all --check    # 只校验，不写库

退出码：0 一致/重建成功；1 发现漂移或重建失败；2 参数/连接错误。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from app.pipeline.projection import compare_projection, records_from_report  # noqa: E402
from app.storage.postgres import PostgresStorage  # noqa: E402


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("缺少 DATABASE_URL")
    return url


async def rebuild(review_id: str | None, *, check: bool, all_reports: bool) -> int:
    storage = PostgresStorage(_database_url())
    failures: list[str] = []
    checked = 0
    try:
        jobs = []
        if review_id:
            job = await storage.get_job(review_id)
            if job is None:
                print(f"[ERROR] review {review_id} 不存在")
                return 2
            jobs = [job]
        elif all_reports:
            jobs = [
                job
                for job in await storage.list_jobs(limit=10000)
                if job.report_json is not None
            ]
        else:
            print("[ERROR] 必须指定 --review 或 --all")
            return 2

        for job in jobs:
            checked += 1
            report = job.report_json or {}
            expected = records_from_report(job.id, report)
            if check:
                actual = await storage.list_issues(job.id)
                problems = compare_projection(job.id, report, actual)
                if problems:
                    failures.append(f"{job.id}: " + "; ".join(problems))
            else:
                await storage.replace_issues(job.id, expected)
                actual = await storage.list_issues(job.id)
                problems = compare_projection(job.id, report, actual)
                if problems:
                    failures.append(f"{job.id}: 重建后仍不一致: " + "; ".join(problems))
    finally:
        await storage.close()

    if failures:
        for failure in failures:
            print(f"[ERROR] {failure}")
        print(f"结果: 失败（检查 {checked} 份报告，{len(failures)} 份不一致）")
        return 1
    action = "校验" if check else "重建并校验"
    print(f"结果: 通过（{action} {checked} 份报告）")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="重建/校验 issues 投影")
    parser.add_argument("--review", help="只处理指定 review_id")
    parser.add_argument("--all", action="store_true", help="处理所有有报告的评审")
    parser.add_argument("--check", action="store_true", help="只校验，不写库")
    args = parser.parse_args()
    return asyncio.run(rebuild(args.review, check=args.check, all_reports=args.all))


if __name__ == "__main__":
    raise SystemExit(main())
