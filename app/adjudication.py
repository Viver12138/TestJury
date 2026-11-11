"""人工裁决工作台：把 AI/静态候选问题转成人工签名的 issue 级标签。

约束：
- 只有 `final.adjudicator` 非空且 `final.validity != pending` 才算已裁决；
- `valid` 必须有 severity 与 category；`invalid`/`uncertain`/`needs_spec` 不填 severity；
- 每次裁决追加 `history.jsonl`，不覆盖历史；YAML 只是当前视图。
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import tempfile
import uuid
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

VALIDITY_VALUES = {"pending", "valid", "invalid", "uncertain", "needs_spec"}
SEVERITY_VALUES = {"blocker", "major", "suggestion"}
CASE_VERDICTS = {"pending", "in_progress", "pass", "needs_fix", "blocked", "uncertain"}
CASE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class AdjudicationError(Exception):
    pass


def case_path(root: Path, case_id: str) -> Path:
    """构造并校验裁决文件路径，禁止 CSV 中的 case_id 路径穿越。"""

    if not CASE_ID_RE.fullmatch(case_id or ""):
        raise AdjudicationError(f"非法 case_id: {case_id!r}")
    root_resolved = Path(root).resolve()
    path = (root_resolved / f"{case_id}.yaml").resolve()
    if path.parent != root_resolved:
        raise AdjudicationError(f"case_id 越界: {case_id!r}")
    return path


def load_case(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "case_id" not in data:
        raise AdjudicationError(f"不是合法裁决文件: {path}")
    return data


def save_case(path: Path, data: dict[str, Any]) -> None:
    """原子写：同目录临时文件 + os.replace，避免半写 YAML。"""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            yaml.safe_dump(data, handle, allow_unicode=True, sort_keys=False)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


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
    if defect_count is not None and (not isinstance(defect_count, int) or defect_count < 0):
        raise AdjudicationError("defect_count 必须是非负整数")
    candidates_list = data.get("candidates", [])
    valid_count = sum(
        1
        for candidate in candidates_list
        if candidate.get("final", {}).get("validity") == "valid"
    )
    pending_count = sum(
        1
        for candidate in candidates_list
        if candidate.get("final", {}).get("validity", "pending") == "pending"
    )
    final_verdicts = {"pass", "needs_fix", "blocked", "uncertain"}
    if verdict in final_verdicts and pending_count:
        raise AdjudicationError(
            f"仍有 {pending_count} 条候选未裁决，不能填写最终结论 {verdict}"
        )
    if defect_count is None:
        defect_count = valid_count
    elif defect_count != valid_count:
        raise AdjudicationError(
            f"defect_count={defect_count} 与 valid 候选数 {valid_count} 不一致"
        )
    if verdict == "pass":
        if valid_count:
            raise AdjudicationError("pass 不允许存在 valid 问题")
        unsettled = [
            candidate
            for candidate in candidates_list
            if candidate.get("final", {}).get("validity") in ("uncertain", "needs_spec")
        ]
        if unsettled:
            raise AdjudicationError("存在 uncertain/needs_spec 候选，不能判 pass")
    if verdict == "needs_fix" and not valid_count:
        raise AdjudicationError("needs_fix 至少需要一条 valid 问题")
    if verdict == "blocked":
        has_blocker = any(
            candidate.get("final", {}).get("validity") == "valid"
            and candidate.get("final", {}).get("severity") == "blocker"
            for candidate in candidates_list
        )
        if not has_blocker:
            raise AdjudicationError("blocked 至少需要一条 valid blocker")
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
    cases_done = cases_in_progress = 0
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
        verdict = data.get("case_level", {}).get("verdict", "pending")
        if verdict == "in_progress":
            cases_in_progress += 1
        elif verdict in {"pass", "needs_fix", "blocked", "uncertain"}:
            cases_done += 1
    return {
        "cases": len(files),
        "cases_done": cases_done,
        "cases_in_progress": cases_in_progress,
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


def _decision_signature(data: dict[str, Any]) -> tuple[Any, ...]:
    """忽略 adjudicated_at 的幂等签名。"""

    candidates = tuple(
        (
            item.get("candidate_id"),
            item.get("final", {}).get("validity"),
            item.get("final", {}).get("severity"),
            item.get("final", {}).get("category"),
            item.get("final", {}).get("correction"),
            item.get("final", {}).get("adjudicator"),
            item.get("final", {}).get("note"),
        )
        for item in data.get("candidates", [])
    )
    level = data.get("case_level", {})
    return (
        candidates,
        level.get("verdict"),
        level.get("defect_count"),
        level.get("adjudicator"),
        level.get("note"),
    )


def import_decisions_from_csv(
    root: Path,
    csv_path: Path,
    *,
    default_adjudicator: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """把填写好的 CSV 合并回 YAML；只合并 final_validity 非空的行走。

    安全与一致性：
    - case_id 走白名单并校验 resolve 后的目录边界，禁止路径穿越；
    - 先对所有行做完整校验并生成内存中的新 YAML，再原子写文件；
    - 校验失败时不会写 history，也不会写半份 YAML；
    - 同一 case 的 case_verdict 必须唯一。
    """

    if not Path(csv_path).exists():
        raise AdjudicationError(f"CSV 不存在: {csv_path}")
    grouped: dict[str, list[dict[str, str]]] = {}
    seen_candidates: set[tuple[str, str]] = set()
    with Path(csv_path).open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            validity = (row.get("final_validity") or "").strip()
            if not validity or validity == "pending":
                continue
            case_id = (row.get("case_id") or "").strip()
            if not case_id:
                raise AdjudicationError("CSV 存在缺 case_id 的已裁决行")
            candidate_id = (row.get("candidate_id") or "").strip()
            if not candidate_id:
                raise AdjudicationError(f"{case_id} 存在缺 candidate_id 的已裁决行")
            key = (case_id, candidate_id)
            if key in seen_candidates:
                raise AdjudicationError(f"CSV 重复候选行: {case_id}/{candidate_id}")
            seen_candidates.add(key)
            grouped.setdefault(case_id, []).append(row)

    prepared: list[tuple[Path, dict[str, Any], list[dict[str, Any]], dict[str, Any], str]] = []
    decided = 0
    for case_id, rows in grouped.items():
        path = case_path(root, case_id)
        if not path.exists():
            raise AdjudicationError(f"CSV 引用了不存在的用例: {case_id}")
        original = load_case(path)
        before_hash = _sha256_file(path)
        data = deepcopy(original)
        case_verdicts: set[str] = set()
        case_verdict_row: dict[str, str] | None = None
        entries: list[dict[str, Any]] = []
        for row in rows:
            adjudicator = (row.get("adjudicator") or default_adjudicator or "").strip()
            if not adjudicator:
                raise AdjudicationError(f"{case_id}/{row.get('candidate_id')} 缺少 adjudicator")
            entries.append(
                record_decision(
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
            )
            decided += 1
            v = (row.get("case_verdict") or "").strip()
            if v and v != "pending":
                case_verdicts.add(v)
                if case_verdict_row is None:
                    case_verdict_row = row
        if len(case_verdicts) > 1:
            raise AdjudicationError(f"{case_id} 的 case_verdict 不一致: {sorted(case_verdicts)}")
        if case_verdict_row is not None:
            verdict = (case_verdict_row.get("case_verdict") or "").strip()
            defect_raw = (case_verdict_row.get("case_defect_count") or "").strip()
            try:
                defect_count = int(defect_raw) if defect_raw else None
            except ValueError as exc:
                raise AdjudicationError(f"{case_id} 的 case_defect_count 不是整数") from exc
            entries.append(
                set_case_verdict(
                    data,
                    verdict=verdict,
                    defect_count=defect_count,
                    adjudicator=(
                        (case_verdict_row.get("adjudicator") or default_adjudicator or "").strip()
                    ),
                    note=(case_verdict_row.get("case_note") or "").strip() or None,
                    at=(case_verdict_row.get("adjudicated_at") or "").strip() or None,
                )
            )
        prepared.append((path, data, entries, original, before_hash))

    if dry_run:
        return {"cases": len(prepared), "decisions": decided, "dry_run": True}

    # 完整幂等：当前 YAML 的裁决内容已与目标一致，不重复写 history
    if all(_decision_signature(load_case(path)) == _decision_signature(data) for path, data, _, _, _ in prepared):
        return {
            "cases": len(prepared),
            "decisions": 0,
            "already_applied": decided,
            "dry_run": False,
        }

    batch_id = uuid.uuid4().hex
    imports_dir = Path(root) / ".imports"
    backup_dir = imports_dir / f"{batch_id}.backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    history_path = Path(root) / "history.jsonl"
    history_backup = imports_dir / f"{batch_id}.history"
    if history_path.exists():
        shutil.copy2(history_path, history_backup)
    journal_path = imports_dir / f"{batch_id}.json"
    journal: dict[str, Any] = {
        "batch_id": batch_id,
        "status": "applying",
        "created_at": datetime.now(UTC).isoformat(),
        "files": [
            {
                "case_id": path.stem,
                "path": path.name,
                "before_hash": before_hash,
            }
            for path, _, _, _, before_hash in prepared
        ],
        "history_existed": history_path.exists(),
        "history_size": history_path.stat().st_size if history_path.exists() else 0,
    }
    _write_json(journal_path, journal)
    written: list[tuple[Path, Path]] = []
    try:
        for path, data, _, _, before_hash in prepared:
            # 写入前再次检查并发修改
            if _sha256_file(path) != before_hash:
                raise AdjudicationError(f"用例文件已被其他人修改: {path.name}")
            backup = backup_dir / path.name
            shutil.copy2(path, backup)
            save_case(path, data)
            written.append((path, backup))
        for _, _, entries, _, _ in prepared:
            for entry in entries:
                entry["batch_id"] = batch_id
                append_history(history_path, entry)
        journal["status"] = "applied"
        journal["applied_at"] = datetime.now(UTC).isoformat()
        _write_json(journal_path, journal)
    except Exception as exc:
        # 失败恢复：还原已写 YAML 与 history，保留失败 journal
        for path, backup in written:
            shutil.copy2(backup, path)
        if history_backup.exists():
            shutil.copy2(history_backup, history_path)
        elif not journal["history_existed"] and history_path.exists():
            history_path.unlink()
        journal["status"] = "failed"
        journal["error"] = str(exc)[:1000]
        _write_json(journal_path, journal)
        if isinstance(exc, AdjudicationError):
            raise
        raise AdjudicationError(f"批次导入失败，已回滚: {exc}") from exc
    return {
        "cases": len(prepared),
        "decisions": decided,
        "dry_run": False,
        "batch_id": batch_id,
    }


def recover_imports(root: Path) -> dict[str, Any]:
    """恢复中断的批次导入：按 journal 的备份还原 YAML 与 history。"""

    imports_dir = Path(root) / ".imports"
    recovered = 0
    failed = 0
    for journal_path in sorted(imports_dir.glob("*.json")):
        try:
            journal = json.loads(journal_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            failed += 1
            continue
        if journal.get("status") != "applying":
            continue
        batch_id = journal.get("batch_id") or journal_path.stem
        backup_dir = imports_dir / f"{batch_id}.backup"
        for entry in journal.get("files", []):
            path = Path(root) / entry["path"]
            backup = backup_dir / entry["path"]
            if backup.exists():
                shutil.copy2(backup, path)
        history_path = Path(root) / "history.jsonl"
        history_backup = imports_dir / f"{batch_id}.history"
        if history_backup.exists():
            shutil.copy2(history_backup, history_path)
        elif not journal.get("history_existed") and history_path.exists():
            history_path.unlink()
        journal["status"] = "recovered"
        journal["recovered_at"] = datetime.now(UTC).isoformat()
        _write_json(journal_path, journal)
        recovered += 1
    return {"recovered": recovered, "failed": failed}

