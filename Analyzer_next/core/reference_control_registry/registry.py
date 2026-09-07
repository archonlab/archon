"""Project ARCHON Reference Control Registry v1.1.

Builds a conservative, provenance-rich registry of reference-control roles
from the normalized Observer profiles. It does not redefine Observer metrics
or scientific claims. One rule may serve several control roles.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

SCHEMA = "archon_reference_control_registry_v1_1"
VERSION = "Reference Control Registry v1.1"

CLASS_ORDER = [
    "credible_emergence",
    "persistent_dynamics",
    "crisis_recovery",
    "fragmented",
    "crystal_static",
    "oscillator",
    "noise_like",
    "extinction",
]

CLASS_TITLES = {
    "credible_emergence": "Credible emergence",
    "persistent_dynamics": "Persistent dynamics",
    "crisis_recovery": "Crisis / recovery",
    "fragmented": "Fragmented",
    "crystal_static": "Crystal / static",
    "oscillator": "Oscillator",
    "noise_like": "Noise-like",
    "extinction": "Extinction",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sf(value: Any, default: float = 0.0) -> float:
    try:
        x = float(value)
        return default if math.isnan(x) or math.isinf(x) else x
    except Exception:
        return default


def si(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def ss(value: Any, default: str = "") -> str:
    return default if value is None else str(value)


def rule_id(value: Any) -> str:
    text = ss(value).strip()
    return text.zfill(5) if text.isdigit() else text


def nested(profile: dict[str, Any], *paths: str) -> Any:
    for path in paths:
        cur: Any = profile
        ok = True
        for key in path.split("."):
            if not isinstance(cur, dict) or key not in cur:
                ok = False
                break
            cur = cur[key]
        if ok and cur is not None:
            return cur
    return None


def text_blob(profile: dict[str, Any]) -> str:
    chunks: list[str] = []
    def walk(value: Any, depth: int = 0) -> None:
        if depth > 4:
            return
        if isinstance(value, str):
            chunks.append(value.lower())
        elif isinstance(value, list):
            for item in value[:100]:
                walk(item, depth + 1)
        elif isinstance(value, dict):
            for key, item in value.items():
                if key.lower() in {"category", "classification", "analyzer_category", "family", "tags", "warnings", "status", "regime", "stage", "key_reasons"}:
                    walk(item, depth + 1)
    walk(profile)
    return " ".join(chunks)


def collapsed(profile: dict[str, Any], blob: str) -> bool:
    raw = nested(profile, "collapse", "passport.collapse")
    if isinstance(raw, bool):
        return raw
    text = ss(raw).strip().lower()
    return text not in {"", "no", "none", "false", "0", "null"} or "collapsed" in blob


def representative_profiles(payload: Any) -> dict[str, dict[str, Any]]:
    profiles = payload.get("profiles", []) if isinstance(payload, dict) else payload
    if not isinstance(profiles, list):
        return {}
    chosen: dict[str, dict[str, Any]] = {}
    for row in profiles:
        if not isinstance(row, dict):
            continue
        rid = rule_id(row.get("rule") or row.get("rule_id"))
        if not rid:
            continue
        rank = (
            int(bool(row.get("is_representative"))),
            sf(nested(row, "layer_stack_score", "scores.layer_stack_score")),
            si(nested(row, "lifetime", "passport.lifetime")),
        )
        previous = chosen.get(rid)
        if previous is None:
            row = dict(row); row["_selection_rank"] = rank; chosen[rid] = row
        elif rank > tuple(previous.get("_selection_rank", (0, 0.0, 0))):
            row = dict(row); row["_selection_rank"] = rank; chosen[rid] = row
    for row in chosen.values():
        row.pop("_selection_rank", None)
    return chosen


def metrics(profile: dict[str, Any]) -> dict[str, Any]:
    """Read only fields that actually exist in normalized Observer Profile v30."""
    blob = text_blob(profile)

    final_tick = si(nested(profile, "final_tick"))
    collapse_tick_raw = nested(profile, "collapse_tick")
    collapse_tick = (
        si(collapse_tick_raw, -1)
        if collapse_tick_raw is not None
        else -1
    )
    longest_age = si(nested(profile, "longest_age"))
    stability = sf(nested(profile, "stability_index"))
    emg = sf(nested(profile, "emergence_score"))
    val = sf(nested(profile, "validation_quality"))
    layer_score = sf(nested(profile, "layer_stack_score"))
    scientific_confidence = ss(
        nested(profile, "scientific_confidence"),
        "NONE",
    ).upper()

    dead = collapse_tick >= 0 or collapsed(profile, blob)

    return {
        "blob": blob,
        "final_tick": final_tick,
        "collapse_tick": collapse_tick,
        "longest_age": longest_age,
        "stability_index": stability,
        "emergence_score": emg,
        "validation_quality": val,
        "layer_stack_score": layer_score,
        "scientific_confidence": scientific_confidence,
        "collapsed": dead,
        "classification": ss(nested(profile, "analyzer_category")),
    }


def classify(profile: dict[str, Any]) -> list[dict[str, Any]]:
    m = metrics(profile)
    b = m["blob"]
    final_tick = m["final_tick"]
    collapse_tick = m["collapse_tick"]
    longest_age = m["longest_age"]
    stability = m["stability_index"]
    emg = m["emergence_score"]
    val = m["validation_quality"]
    layer = m["layer_stack_score"]
    sci = m["scientific_confidence"]
    dead = m["collapsed"]
    roles: list[dict[str, Any]] = []

    def add(cid: str, score: float, qualified: bool, reasons: list[str]) -> None:
        roles.append({
            "class_id": cid,
            "score": round(max(0.0, min(1.0, score)), 4),
            "qualified": bool(qualified),
            "reasons": reasons,
        })

    explicit_emg = (
        "credible_emerg" in b
        or ("credible" in b and "emerg" in b)
    )
    if explicit_emg or (emg >= 0.60 and val >= 0.70):
        add(
            "credible_emergence",
            0.40 * emg + 0.35 * val + 0.15 * layer + 0.10 * (not dead),
            (
                emg >= 0.72
                and val >= 0.90
                and sci in {"HIGH", "VERY_HIGH"}
                and not dead
            ),
            [
                f"EMG={emg:.3f}",
                f"VAL={val:.3f}",
                f"layer={layer:.3f}",
                f"scientific_confidence={sci}",
                f"collapsed={dead}",
            ],
        )

    explicit_persist = any(
        x in b
        for x in (
            "persistent",
            "long-lived",
            "stable dynamic attractor",
            "adaptive_feedback",
        )
    )
    if explicit_persist or (final_tick >= 100_000 and not dead):
        add(
            "persistent_dynamics",
            (
                0.55 * min(1.0, final_tick / 400_000)
                + 0.20 * stability
                + 0.15 * val
                + 0.10 * (not dead)
            ),
            (
                final_tick >= 200_000
                and val >= 0.75
                and not dead
            ),
            [
                f"final_tick={final_tick}",
                f"stability={stability:.3f}",
                f"VAL={val:.3f}",
                f"collapsed={dead}",
            ],
        )

    explicit_recovery = any(
        x in b
        for x in ("crisis", "recovery", "recovered", "revival", "resilien")
    )
    if explicit_recovery:
        add(
            "crisis_recovery",
            0.50 + 0.25 * val + 0.25 * min(1.0, final_tick / 100_000),
            val >= 0.70 and final_tick >= 10_000 and not dead,
            [
                "explicit crisis/recovery signal",
                f"VAL={val:.3f}",
                f"final_tick={final_tick}",
            ],
        )

    explicit_fragment = any(
        x in b for x in ("fragment", "dispersed", "multi-cluster")
    )
    if explicit_fragment:
        add(
            "fragmented",
            0.55 + 0.20 * stability + 0.25 * min(1.0, final_tick / 50_000),
            final_tick >= 10_000,
            [
                "explicit fragmentation signal",
                f"stability={stability:.3f}",
                f"final_tick={final_tick}",
            ],
        )

    explicit_crystal = any(
        x in b for x in ("crystal", "static", "frozen", "fixed point")
    )
    if explicit_crystal:
        add(
            "crystal_static",
            0.55 + 0.20 * stability + 0.25 * min(1.0, final_tick / 100_000),
            final_tick >= 50_000 and not dead,
            [
                "explicit crystal/static signal",
                f"stability={stability:.3f}",
                f"final_tick={final_tick}",
            ],
        )

    # Observer Profile v30 does not expose Passport Analyzer's breathing_score.
    # Therefore oscillators are accepted only from explicit normalized evidence,
    # rather than silently rebuilding a second periodicity metric here.
    explicit_osc = any(
        x in b for x in ("oscillat", "periodic", "breathing attractor")
    )
    if explicit_osc:
        add(
            "oscillator",
            0.55 + 0.20 * val + 0.25 * min(1.0, final_tick / 100_000),
            final_tick >= 50_000 and val >= 0.70 and not dead,
            [
                "explicit oscillation/periodicity signal",
                f"VAL={val:.3f}",
                f"final_tick={final_tick}",
            ],
        )

    explicit_noise = any(
        x in b for x in ("noise", "chaotic", "random-like", "turbulent")
    )
    if explicit_noise:
        add(
            "noise_like",
            0.55 + 0.20 * (1.0 - val) + 0.25 * min(1.0, final_tick / 50_000),
            final_tick >= 10_000,
            [
                "explicit noise/chaos signal",
                f"VAL={val:.3f}",
                f"final_tick={final_tick}",
            ],
        )

    if dead:
        observed_until = (
            collapse_tick
            if collapse_tick >= 0
            else final_tick
        )
        add(
            "extinction",
            0.55 + 0.45 * (1 - min(1.0, observed_until / 10_000)),
            observed_until <= 5_000,
            [
                "collapse detected",
                f"collapse_tick={collapse_tick}",
                f"final_tick={final_tick}",
                f"longest_age={longest_age}",
            ],
        )

    return sorted(
        roles,
        key=lambda x: (x["qualified"], x["score"]),
        reverse=True,
    )


def build_registry(payload: Any, source: str = "memory://observer_profiles_v30.json") -> dict[str, Any]:
    profiles = representative_profiles(payload)
    classes = {
        cid: {
            "class_id": cid,
            "title": CLASS_TITLES[cid],
            "status": "unobserved",
            "candidate_count": 0,
            "qualified_count": 0,
            "candidates": [],
            "qualification_rule": "At least 3 qualified independent rules",
        }
        for cid in CLASS_ORDER
    }
    assignments: dict[str, list[dict[str, Any]]] = {}
    for rid, profile in sorted(profiles.items()):
        roles = classify(profile)
        if roles:
            assignments[rid] = roles
        m = metrics(profile)
        for role in roles:
            row = {
                "rule_id": rid,
                "score": role["score"],
                "qualified": role["qualified"],
                "reasons": role["reasons"],
                "source_classification": m["classification"],
                "final_tick": m["final_tick"],
                "collapse_tick": m["collapse_tick"],
                "longest_age": m["longest_age"],
            }
            classes[role["class_id"]]["candidates"].append(row)

    observed = qualified = 0
    for cid in CLASS_ORDER:
        item = classes[cid]
        item["candidates"].sort(key=lambda x: (x["qualified"], x["score"], x["final_tick"]), reverse=True)
        item["candidate_count"] = len(item["candidates"])
        item["qualified_count"] = sum(1 for x in item["candidates"] if x["qualified"])
        if item["qualified_count"] >= 3:
            item["status"] = "qualified"
            observed += 1; qualified += 1
        elif item["candidate_count"]:
            item["status"] = "observed"
            observed += 1

    return {
        "schema": SCHEMA,
        "version": VERSION,
        "generated_at": now_iso(),
        "source": {"observer_profiles": source},
        "method": {
            "principle": "Reuse normalized Observer fields; do not redefine EMG, VAL, families, or scientific claims.",
            "multi_role": True,
            "observed_definition": "At least one candidate rule.",
            "qualified_definition": "At least three independent rules satisfying the class-specific strong criterion.",
        },
        "summary": {
            "independent_rules": len(profiles),
            "class_count": len(CLASS_ORDER),
            "observed_classes": observed,
            "qualified_classes": qualified,
            "unobserved_classes": len(CLASS_ORDER)-observed,
            "assignment_rules": len(assignments),
        },
        "classes": classes,
        "assignments": assignments,
    }


def render_md(data: dict[str, Any]) -> str:
    s=data["summary"]
    lines=[
        "# Project ARCHON Reference Control Registry v1.1", "",
        "This registry reuses normalized Observer evidence. It does not create a second classification system.", "",
        "## Coverage", "",
        f"- Independent rules: **{s['independent_rules']}**",
        f"- Observed classes: **{s['observed_classes']} / {s['class_count']}**",
        f"- Qualified classes: **{s['qualified_classes']} / {s['class_count']}**", "",
        "| Class | Status | Candidates | Qualified | Top rules |", "| --- | --- | ---: | ---: | --- |",
    ]
    marks={"qualified":"✓", "observed":"⚠", "unobserved":"✗"}
    for cid in CLASS_ORDER:
        item=data["classes"][cid]
        top=", ".join(x["rule_id"] for x in item["candidates"][:5]) or "-"
        lines.append(f"| {marks[item['status']]} {item['title']} | {item['status']} | {item['candidate_count']} | {item['qualified_count']} | {top} |")
    lines += ["", "## Interpretation", "", "`Observed` means the regime exists in current data. `Qualified` requires at least three strong independent representatives and is suitable for routine control comparisons.", ""]
    return "\n".join(lines)
