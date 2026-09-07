#!/usr/bin/env python3
"""
Universe Search Research Bridge v24.4

Safe bridge from Analyzer / Research Director into Universe Search.
v24.4 keeps scoring unchanged and acts as an intent-only bridge:
- finds and reads next_research_actions.json
- normalizes Research Director actions and metadata
- writes a bridge status snapshot into the results folder
- provides neutral baseline ratios; EvolutionPolicy is the sole ratio owner

If no Research Director outputs exist, legacy search continues unchanged.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


BRIDGE_VERSION = "v24.4 Research Intent Bridge"

DEFAULT_RATIOS = {"explore": 0.35, "exploit": 0.45, "control": 0.20}


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def _safe_int(x: Any, default: int = 0) -> int:
    try:
        if x is None:
            return default
        return int(x)
    except Exception:
        return default


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        if path.exists() and path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"_bridge_error": f"failed to read {path}: {e!r}"}
    return None


@dataclass
class ResearchPlan:
    active: bool = False
    mode: str = "legacy"
    source: Optional[str] = None
    version: str = BRIDGE_VERSION
    stage: str = "unknown"
    maturity: float = 0.0
    risk: float = 0.0
    rules: int = 0
    principles: int = 0
    consensus: int = 0
    trend: str = "unknown"
    actions: List[Dict[str, Any]] = field(default_factory=list)
    action_types: List[str] = field(default_factory=list)
    priorities: List[str] = field(default_factory=list)
    ratios: Dict[str, float] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "active": self.active,
            "mode": self.mode,
            "source": self.source,
            "version": self.version,
            "stage": self.stage,
            "maturity": self.maturity,
            "risk": self.risk,
            "rules": self.rules,
            "principles": self.principles,
            "consensus": self.consensus,
            "trend": self.trend,
            "actions": self.actions,
            "action_types": self.action_types,
            "priorities": self.priorities,
            "ratios": self.ratios,
            "notes": self.notes,
            "errors": self.errors,
        }


def candidate_action_paths(script_dir: Optional[Path] = None, cwd: Optional[Path] = None) -> List[Path]:
    """Return paths in compatibility order, without assuming one perfect folder layout."""
    cwd = Path(cwd or Path.cwd()).resolve()
    script_dir = Path(script_dir or cwd).resolve()
    roots = []
    for p in [cwd, script_dir, script_dir.parent, cwd.parent]:
        if p not in roots:
            roots.append(p)

    rels = [
        # Current Project ARCHON modular layout. Keep this first.
        Path("Results") / "Analysis" / "next_research_actions.json",
        # Legacy layouts retained for old runs and portable copies.
        Path("analyze_results_v29") / "next_research_actions.json",
        Path("universe_search_v23_results") / "next_research_actions.json",
        Path("next_research_actions.json"),
        Path("analyze_results_v29_modular_bootstrap") / "analyze_results_v29" / "next_research_actions.json",
        Path("analyze_results_v29_modular_bootstrap") / "universe_search_v23_results" / "next_research_actions.json",
    ]
    out: List[Path] = []
    for root in roots:
        for rel in rels:
            path = (root / rel).resolve()
            if path not in out:
                out.append(path)
    return out


def _extract_actions(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Support several likely JSON shapes from Research Director."""
    if not isinstance(payload, dict):
        return []
    for key in ("actions", "next_actions", "priorities", "research_actions"):
        v = payload.get(key)
        if isinstance(v, list):
            return [x for x in v if isinstance(x, dict)]
    # Some reports store state.next_actions.
    state = payload.get("state")
    if isinstance(state, dict):
        for key in ("actions", "next_actions", "priorities"):
            v = state.get(key)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
    return []


def _action_label(action: Dict[str, Any]) -> str:
    for key in ("title", "name", "action", "id", "type", "kind"):
        val = action.get(key)
        if val:
            return str(val)
    return "unknown_action"


def _infer_ratios(actions: List[Dict[str, Any]], risk: float, maturity: float) -> Dict[str, float]:
    """Compatibility shim returning neutral baseline ratios.

    ResearchBridge no longer interprets actions into search pressure. The
    EvolutionPolicy module is the single owner of explore/exploit/control
    calculation, including action, risk, maturity, trend, and cycle intent.
    """
    return dict(DEFAULT_RATIOS)


def build_plan_from_payload(payload: Dict[str, Any], source: Path) -> ResearchPlan:
    errors: List[str] = []
    if "_bridge_error" in payload:
        errors.append(str(payload["_bridge_error"]))

    actions = _extract_actions(payload)
    state = payload.get("state") if isinstance(payload.get("state"), dict) else payload
    stage = str(state.get("stage") or state.get("research_stage") or payload.get("stage") or "unknown")
    maturity = _safe_float(state.get("maturity", state.get("knowledge_maturity", payload.get("maturity", 0.0))))
    risk = _safe_float(state.get("risk", payload.get("risk", 0.0)))
    rules = _safe_int(state.get("rules", state.get("rules_analyzed", payload.get("rules", 0))))
    principles = _safe_int(state.get("principles", payload.get("principles", 0)))
    consensus = _safe_int(state.get("consensus", payload.get("consensus", 0)))
    trend = str(state.get("trend") or payload.get("trend") or "unknown")

    labels = [_action_label(a) for a in actions]
    action_types = sorted({str(a.get("type") or a.get("mode") or a.get("kind") or "unknown") for a in actions})
    ratios = dict(DEFAULT_RATIOS)

    notes = []
    if actions:
        notes.append(f"loaded {len(actions)} director action(s) as normalized intent")
    else:
        notes.append("director file found, but no actions were recognized")
    if risk >= 0.65:
        notes.append("high research risk: keep exploration/control coverage")
    if rules < 10:
        notes.append("few independent rules: avoid promoting principles too early")
    notes.append("EvolutionPolicy is the sole owner of explore/exploit/control adjustments")

    return ResearchPlan(
        active=True,
        mode="research_guided_selection",
        source=str(source),
        stage=stage,
        maturity=round(maturity, 6),
        risk=round(risk, 6),
        rules=rules,
        principles=principles,
        consensus=consensus,
        trend=trend,
        actions=actions,
        action_types=action_types,
        priorities=labels,
        ratios=ratios,
        notes=notes,
        errors=errors,
    )


def load_research_plan(script_dir: Optional[Path] = None, cwd: Optional[Path] = None, verbose: bool = True) -> ResearchPlan:
    for path in candidate_action_paths(script_dir=script_dir, cwd=cwd):
        payload = _read_json(path)
        if payload is not None:
            plan = build_plan_from_payload(payload, path)
            if verbose:
                print_research_plan(plan)
            return plan

    plan = ResearchPlan(
        active=False,
        mode="legacy",
        notes=["no next_research_actions.json found; using legacy search"],
        ratios={"explore": 0.0, "exploit": 0.0, "control": 0.0},
    )
    if verbose:
        print_research_plan(plan)
    return plan


def print_research_plan(plan: ResearchPlan) -> None:
    print("[ResearchBridge]", BRIDGE_VERSION)
    if not plan.active:
        print("[ResearchBridge] no director plan found; using legacy search")
        return
    print(f"[ResearchBridge] loaded: {plan.source}")
    print(f"[ResearchBridge] mode={plan.mode} stage={plan.stage} maturity={plan.maturity:.3f} risk={plan.risk:.3f} trend={plan.trend}")
    if plan.priorities:
        print("[ResearchBridge] priorities:")
        for i, p in enumerate(plan.priorities[:6], 1):
            print(f"  R{i}: {p}")
    if plan.ratios:
        print(f"[ResearchBridge] baseline ratios: explore={plan.ratios.get('explore',0):.2f} exploit={plan.ratios.get('exploit',0):.2f} control={plan.ratios.get('control',0):.2f} (owned by EvolutionPolicy)")
    for err in plan.errors:
        print(f"[ResearchBridge] warning: {err}")


def write_bridge_status(results_dir: Path, plan: ResearchPlan) -> Path:
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    path = results_dir / "research_bridge_status.json"
    payload = plan.to_dict()
    payload["written_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return path


def write_selection_status(results_dir: Path, payload: Dict[str, Any]) -> Path:
    """Append a compact per-generation guided-selection snapshot."""
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    path = results_dir / "research_guided_selection_log.json"
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                data = []
        else:
            data = []
    except Exception:
        data = []
    item = dict(payload)
    item["written_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    data.append(item)
    data = data[-200:]
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return path


if __name__ == "__main__":
    p = load_research_plan(script_dir=Path(__file__).resolve().parent, cwd=Path.cwd(), verbose=True)
    print(json.dumps(p.to_dict(), indent=2, ensure_ascii=False))
