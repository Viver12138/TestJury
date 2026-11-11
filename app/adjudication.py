"""人工裁决工作台：把 AI/静态候选问题转成人工签名的 issue 级标签。

约束：
- 只有 `final.adjudicator` 非空且 `final.validity != pending` 才算已裁决；
- `valid` 必须有 severity 与 category；`invalid`/`uncertain`/`needs_spec` 不填 severity；
- 每次裁决追加 `history.jsonl`，不覆盖历史；YAML 只是当前视图。
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

VALIDITY_VALUES = {"pending", "valid", "invalid", "uncertain", "needs_spec"}
SEVERITY_VALUES = {"blocker", "major", "suggestion"}
CASE_VERDICTS = {"pending", "pass", "needs_fix", "blocked", "uncertain"}


class AdjudicationError(Exception):
    pass


def load_case(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "case_id" not in data:
        raise AdjudicationError(f"不是合法裁决文件: {path}")
    return data


def save_case(path: Path, data: dict[str, Any]) -> None:
    Path(path).write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )


def _find_candidate(data: dict[str, Any], candidate_id: str) -> dict[str, Any]:
    for candidate in data.get("candidates", []):
        if candidate.get("candidate_id") == candidate_id:
            return candidate
    raise AdjudicationError(f"candidate 不存在: {candidate_id}")


def record_decision(
    data: dict[str, Any],
    candidate_id: str,
    *,
    validity: str,
    severity: str | None = None,
    category: str | None = None,
    correction: str | None = None,
    adjudicator: str,
    note: str | None = None,
    at: str | None = None,
) -> dict[str, Any]:
    if validity not in VALIDITY_VALUES - {"pending"}:
        raise AdjudicationError(f"非法 validity: {validity!r}")
    if not adjudicator or not adjudicator.strip():
        raise AdjudicationError("adjudicator 必填；AI 不能代替人工签名")
    if validity == "valid":
        if severity not in SEVERITY_VALUES:
            raise AdjudicationError("valid 必须给出 severity（blocker/major/suggestion）")
        if not category or not category.strip():
            raise AdjudicationError("valid 必须给出 category")
    else:
        if severity is not None:
            raise AdjudicationError(f"{validity} 不应填写 severity")
        severity = None
    candidate = _find_candidate(data, candidate_id)
    final = candidate.setdefault("final", {})
    previous = final.get("validity", "pending")
    final.update(
        {
            "validity": validity,
            "severity": severity,
            "category": category.strip() if category else None,
            "correction": correction,
            "adjudicator": adjudicator.strip(),
            "adjudicated_at": at or datetime.now(UTC).isoformat(),
            "note": note,
        }
    )
    return {
        "case_id": data["case_id"],
        "candidate_id": candidate_id,
        "from": previous,
        "to": validity,
        "severity": severity,
        "adjudicator": adjudicator.strip(),
        "at": final["adjudicated_at"],
        "note": note,
    }


def set_case_verdict(
    data: dict[str, Any],
    *,
    verdict: str,
    adjudicator: str,
    defect_count: int | None = None,
    note: str | None = None,
    at: str | None = None,
) -> dict[str, Any]:
    if verdict not in CASE_VERDICTS - {"pending"}:
        raise AdjudicationError(f"非法用例结论: {verdict!r}")
    if not adjudicator or not adjudicator.strip():
        raise AdjudicationError("adjudicator 必填")
    level = data.setdefault("case_level", {})
    level.update(
        {
            "verdict": verdict,
            "defect_count": defect_count,
            "adjudicator": adjudicator.strip(),
            "adjudicated_at": at or datetime.now(UTC).isoformat(),
            "note": note,
        }
    )
    return {"case_id": data["case_id"], "verdict": verdict, "adjudicator": adjudicator}


def append_history(path: Path, entry: dict[str, Any]) -> None:
    import json

    with Path(path).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def stats(root: Path) -> dict[str, Any]:
    files = sorted(Path(root).glob("*.yaml"))
    total = decided = valid = invalid = needs_spec = pending = 0
    cases_done = 0
    for path in files:
        data = load_case(path)
        case_candidates = data.get("candidates", [])
        total += len(case_candidates)
        for candidate in case_candidates:
            validity = candidate.get("final", {}).get("validity", "pending")
            if validity == "pending":
                pending += 1
            else:
                decided += 1
                if validity == "valid":
                    valid += 1
                elif validity == "invalid":
                    invalid += 1
                elif validity == "needs_spec":
                    needs_spec += 1
        if data.get("case_level", {}).get("verdict", "pending") != "pending":
            cases_done += 1
    return {
        "cases": len(files),
        "cases_done": cases_done,
        "candidates": total,
        "decided": decided,
        "pending": pending,
        "valid": valid,
        "invalid": invalid,
        "needs_spec": needs_spec,
    }


def export_csv(root: Path, destination: Path) -> int:
    rows: list[dict[str, Any]] = []
    for path in sorted(Path(root).glob("*.yaml")):
        data = load_case(path)
        level = data.get("case_level", {})
        for candidate in data.get("candidates", []):
            final = candidate.get("final", {})
            rows.append(
                {
                    "case_id": data["case_id"],
                    "case_title": data.get("case_title"),
                    "candidate_id": candidate["candidate_id"],
                    "title": candidate.get("title"),
                    "claim": candidate.get("claim"),
                    "evidence_case": candidate.get("evidence_case"),
                    "evidence_spec": candidate.get("evidence_spec"),
                    "ai_recommendation": candidate.get("ai_recommendation"),
                    "ai_reason": candidate.get("ai_reason"),
                    "ai_suggested_severity": candidate.get("ai_suggested_severity"),
                    "final_validity": final.get("validity", "pending"),
                    "final_severity": final.get("severity") or "",
                    "final_category": final.get("category") or "",
                    "correction": final.get("correction") or "",
                    "adjudicator": final.get("adjudicator") or "",
                    "adjudicated_at": final.get("adjudicated_at") or "",
                    "note": final.get("note") or "",
                    "case_verdict": level.get("verdict", "pending"),
                    "case_defect_count": level.get("defect_count")
                    if level.get("defect_count") is not None
                    else "",
                    "case_note": level.get("note") or "",
                }
            )
    if not rows:
        raise AdjudicationError("没有可导出的用例")
    try:
        with Path(destination).open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    except PermissionError as exc:
        raise AdjudicationError(
            f"CSV 被占用（Excel/WPS 打开中），请关闭后重试: {destination}"
        ) from exc
    return len(rows)


def import_decisions_from_csv(
    root: Path,
    csv_path: Path,
    *,
    default_adjudicator: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """把填写好的 CSV 合并回 YAML；只合并 final_validity 非空的行走。

    CSV 以 `candidate_id` 为键；同一 case 的 case_verdict/case_defect_count 取第一行非空值。
    每合并一条候选写一条 history，不覆盖已有裁决以外的历史。
    """

    if not Path(csv_path).exists():
        raise AdjudicationError(f"CSV 不存在: {csv_path}")
    grouped: dict[str, list[dict[str, str]]] = {}
    with Path(csv_path).open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            validity = (row.get("final_validity") or "").strip()
            if not validity or validity == "pending":
                continue
            case_id = (row.get("case_id") or "").strip()
            if not case_id:
                raise AdjudicationError("CSV 存在缺 case_id 的已裁决行")
            grouped.setdefault(case_id, []).append(row)

    decided = 0
    cases = 0
    for case_id, rows in grouped.items():
        path = Path(root) / f"{case_id}.yaml"
        if not path.exists():
            raise AdjudicationError(f"CSV 引用了不存在的用例: {case_id}")
        data = load_case(path)
        case_verdict_row = next(
            (row for row in rows if (row.get("case_verdict") or "").strip() not in ("", "pending")),
            None,
        )
        for row in rows:
            adjudicator = (row.get("adjudicator") or default_adjudicator or "").strip()
            if not adjudicator:
                raise AdjudicationError(f"{case_id}/{row.get('candidate_id')} 缺少 adjudicator")
            entry = record_decision(
                data,
                (row.get("candidate_id") or "").strip(),
                validity=(row.get("final_validity") or "").strip(),
                severity=(row.get("final_severity") or "").strip() or None,
                category=(row.get("final_category") or "").strip() or None,
                correction=(row.get("correction") or "").strip() or None,
                adjudicator=adjudicator,
                note=(row.get("note") or "").strip() or None,
                at=(row.get("adjudicated_at") or "").strip() or None,
            )
            if not dry_run:
                append_history(Path(root) / "history.jsonl", entry)
            decided += 1
        if case_verdict_row is not None:
            verdict = (case_verdict_row.get("case_verdict") or "").strip()
            defect_raw = (case_verdict_row.get("case_defect_count") or "").strip()
            set_case_verdict(
                data,
                verdict=verdict,
                defect_count=int(defect_raw) if defect_raw else None,
                adjudicator=(
                    (case_verdict_row.get("adjudicator") or default_adjudicator or "").strip()
                ),
                note=(case_verdict_row.get("case_note") or "").strip() or None,
                at=(case_verdict_row.get("adjudicated_at") or "").strip() or None,
            )
        if not dry_run:
            save_case(path, data)
        cases += 1
    return {"cases": cases, "decisions": decided, "dry_run": dry_run}

