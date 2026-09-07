"""Rule catalog, durable JSON helpers, and research-cycle discovery."""
from __future__ import annotations

from .settings import *


from Analyzer_next.adapters.observer.path_opener import open_path


# The observer imports this catalog after settings, so the stable modular
# handoff entrypoint is the effective production route without rewriting the
# protected legacy launcher contract.
PRODUCTION_LAUNCHER_HANDOFF = (
    PROJECT_ROOT
    / "Analyzer_next"
    / "cli"
    / "production_research_cycle_launcher_handoff.py"
)


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)

def canonical_hash(payload: Any) -> str:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def load_research_cycle_catalog(
    records_root: Path = RESEARCH_CYCLE_RECORDS_ROOT,
) -> dict[str, Any]:
    records_root = Path(records_root)
    index_path = records_root / "research_cycle_index.json"
    records_dir = records_root / "records"
    index = read_json(index_path, {})
    if not isinstance(index, dict):
        index = {}
    index_rows = [
        row
        for row in index.get("records", [])
        if isinstance(row, dict)
    ]
    index_verified = bool(
        index
        and index.get("content_hash")
        and index.get("content_hash") == canonical_hash(index_rows)
    )

    records: list[dict[str, Any]] = []
    invalid_count = 0
    missing_count = 0
    for index_row in index_rows:
        cycle_id = str(index_row.get("cycle_id") or "").strip()
        if not cycle_id or not all(
            character.isalnum() or character in "_.-"
            for character in cycle_id
        ):
            invalid_count += 1
            continue
        record_path = records_dir / f"{cycle_id}.json"
        record = read_json(record_path, {})
        if not isinstance(record, dict) or not record:
            missing_count += 1
            records.append(
                {
                    **index_row,
                    "cycle_id": cycle_id,
                    "current_stage": (
                        index_row.get("current_stage")
                        or "RECORD_MISSING"
                    ),
                    "next_required_action": "REBUILD_CYCLE_RECORDS",
                    "receipt_integrity": "NOT_VERIFIED",
                    "blockers": ["AUTHORITATIVE_RECORD_MISSING"],
                    "record_verified": False,
                    "record_path": str(record_path),
                }
            )
            continue

        declared_hash = record.get("record_hash")
        record_core = {
            key: value
            for key, value in record.items()
            if key != "record_hash"
        }
        record_verified = bool(
            declared_hash
            and declared_hash == canonical_hash(record_core)
            and declared_hash == index_row.get("record_hash")
        )
        if not record_verified:
            invalid_count += 1
        records.append(
            {
                **record,
                "record_verified": record_verified,
                "record_path": str(record_path),
            }
        )

    records.sort(
        key=lambda item: str(item.get("updated_at") or ""),
        reverse=True,
    )
    return {
        "available": bool(index),
        "index_path": str(index_path),
        "index_verified": index_verified,
        "count": len(records),
        "blocked_count": sum(
            1 for record in records if record.get("blockers")
        ),
        "invalid_count": invalid_count,
        "missing_count": missing_count,
        "records": records,
    }

def normalize_rule_id(value: Any) -> str:
    try:
        return f"{int(value):05d}"
    except Exception:
        return str(value)

def format_score(value: Any) -> str:
    return f"{value:.3f}" if isinstance(value, (int, float)) else ""

def find_rule_file(rule_id: int) -> Path | None:
    matches = sorted(
        WORLD_ATLAS_DIR.rglob(f"rule_{rule_id:05d}_*/rule.json")
    )
    return matches[0] if matches else None

def observation_summary(rule_id: int) -> dict[str, Any]:
    logs = SEARCH_RESULTS_DIR / "observation_logs"
    candidates = []
    if logs.exists():
        candidates = sorted(
            logs.glob(f"rule_{rule_id:05d}_*"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    mutation_base = MUTATION_ROOT / f"rule_{rule_id:05d}"
    mutation_dirs = (
        sorted(
            [p for p in mutation_base.glob("MUT-*") if p.is_dir()],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if mutation_base.exists()
        else []
    )
    latest_time = None
    paths = candidates + mutation_dirs
    if paths:
        latest_time = datetime.fromtimestamp(
            max(p.stat().st_mtime for p in paths)
        )
    return {
        "observed": bool(candidates),
        "observation_files": len(candidates),
        "mutation_runs": len(mutation_dirs),
        "last_run": (
            latest_time.strftime("%Y-%m-%d %H:%M")
            if latest_time else "-"
        ),
    }

def load_rules() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    index_path = WORLD_ATLAS_DIR / "atlas_index.json"
    index = read_json(index_path, [])

    if isinstance(index, list):
        for entry in index:
            if not isinstance(entry, dict):
                continue
            try:
                rid = int(entry.get("rule_id"))
            except Exception:
                continue
            metrics = entry.get("metrics", {})
            if not isinstance(metrics, dict):
                metrics = {}
            folder = entry.get("folder")
            rows.append({
                "rule_id": rid,
                "score": entry.get("score", metrics.get("score")),
                "class": entry.get(
                    "class",
                    metrics.get("class", metrics.get("world_class", "")),
                ),
                "folder": folder,
                "genome_hash": entry.get("key") or entry.get("genome_hash"),
                "parents": (
                    entry.get("parent_a"),
                    entry.get("parent_b"),
                ),
            })

    if not rows:
        for rule_file in WORLD_ATLAS_DIR.rglob("rule.json"):
            payload = read_json(rule_file, {})
            if not isinstance(payload, dict):
                continue
            try:
                rid = int(payload["rule_id"])
            except Exception:
                continue
            rows.append({
                "rule_id": rid,
                "score": None,
                "class": rule_file.parent.parent.name,
                "folder": str(rule_file.parent),
                "genome_hash": rule_file.parent.name.rsplit("_", 1)[-1],
                "parents": (
                    payload.get("parent_a"),
                    payload.get("parent_b"),
                ),
            })

    by_id: dict[int, dict[str, Any]] = {}
    for row in rows:
        rid = int(row["rule_id"])
        row.update(observation_summary(rid))
        by_id[rid] = row
    return sorted(by_id.values(), key=lambda x: x["rule_id"])
