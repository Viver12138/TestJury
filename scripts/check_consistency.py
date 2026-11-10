"""数据一致性检查（docs/14 §9）：报告投影、人工决定、候选映射、附件绑定。

用法：`DATABASE_URL=... python scripts/check_consistency.py [--review <id>]`
退出码：0 一致；1 发现不一致；2 连接/参数错误。
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

from app.pipeline.projection import compare_projection  # noqa: E402
from app.storage.postgres import PostgresStorage  # noqa: E402


async def check(review_id: str | None) -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("[ERROR] 缺少 DATABASE_URL")
        return 2
    storage = PostgresStorage(url)
    failures: list[str] = []
    checked = 0
    try:
        if review_id:
            job = await storage.get_job(review_id)
            if job is None:
                print(f"[ERROR] review {review_id} 不存在")
                return 2
            jobs = [job]
        else:
            jobs = await storage.list_jobs(limit=10000)

        for job in jobs:
            checked += 1
            if job.report_json is not None:
                if job.report_locked_at is None:
                    failures.append(f"{job.id}: report_json 存在但 report_locked_at 为空")
                problems = compare_projection(
                    job.id, job.report_json, await storage.list_issues(job.id)
                )
                failures.extend(f"{job.id}: {problem}" for problem in problems)

                candidates = {item.id for item in await storage.list_candidates(job.id)}
                for issue in await storage.list_issues(job.id):
                    if issue.candidate_id and issue.candidate_id not in candidates:
                        failures.append(
                            f"{job.id}: ISSUE-{issue.issue_no:03d} 引用了不存在的候选 {issue.candidate_id}"
                        )

            decisions = await storage.list_decisions(job.id)
            if decisions:
                latest = max(decisions, key=lambda item: item.decision_no)
                expected = {
                    "approve": "approved",
                    "reject": "rejected",
                    "request_changes": "changes_requested",
                }[latest.decision]
                if job.human_status != expected:
                    failures.append(
                        f"{job.id}: human_status={job.human_status} 与最新决定 {latest.decision} 不一致"
                    )
                if job.current_decision_id != latest.id:
                    failures.append(
                        f"{job.id}: current_decision_id 未指向最新决定 {latest.id}"
                    )

            for attachment in await storage.list_review_attachments(job.id):
                if attachment.status != "ready":
                    failures.append(
                        f"{job.id}: 绑定了非 ready 附件 {attachment.id}"
                    )
    finally:
        await storage.close()

    if failures:
        for failure in failures:
            print(f"[ERROR] {failure}")
        print(f"结果: 失败（检查 {checked} 份评审，{len(failures)} 项不一致）")
        return 1
    print(f"结果: 通过（检查 {checked} 份评审）")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="数据一致性检查")
    parser.add_argument("--review", help="只检查指定 review_id")
    args = parser.parse_args()
    return asyncio.run(check(args.review))


if __name__ == "__main__":
    raise SystemExit(main())
