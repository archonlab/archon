#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
passport_analyzer.py

Analyze Universe Search Life Passport .md files.

Usage:
    python passport_analyzer.py rule_00251_20260702_163309_passport.md
    python passport_analyzer.py passports_folder
    python passport_analyzer.py passport.md --out passport_analysis.md
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Optional


@dataclass
class Event:
    tick: int
    kind: str
    objects_before: Optional[int] = None
    objects_after: Optional[int] = None
    largest: Optional[int] = None


@dataclass
class PassportAnalysis:
    file: str
    rule: str
    score: Optional[float]
    last_alive_tick: Optional[int]
    collapse_tick: Optional[int]
    longest_observed_age: Optional[int]
    peak_objects: Optional[int]
    peak_largest: Optional[int]
    total_center_drift: Optional[float]
    final_stage: Optional[str]
    identity_persistence: Optional[float]
    legacy_score: Optional[float]
    information_survival: Optional[float]
    events_total: int
    split_birth_events: int
    merge_death_events: int
    object_min: Optional[int]
    object_max: Optional[int]
    object_range: Optional[int]
    mean_event_interval: Optional[float]
    median_event_interval: Optional[float]
    event_interval_std: Optional[float]
    breathing_score: float
    long_life_score: float
    turnover_balance_score: float
    dynamic_attractor_score: float
    classification: str
    interpretation: str


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def grab(text: str, label: str) -> Optional[str]:
    patterns = [
        rf"{re.escape(label)}:\s*\*\*([^*]+)\*\*",
        rf"{re.escape(label)}:\s*([^\n]+)",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            raw = m.group(1).strip()
            if raw.lower() in {"none", "null", "nan", ""}:
                return None
            return raw
    return None


def grab_float(text: str, label: str) -> Optional[float]:
    raw = grab(text, label)
    if raw is None:
        return None
    try:
        return float(raw.replace(",", ""))
    except ValueError:
        return None


def grab_int(text: str, label: str) -> Optional[int]:
    val = grab_float(text, label)
    return int(val) if val is not None else None


def observed_lifetime(longest: Optional[int], last_alive: Optional[int]) -> int:
    """Preserve measured zero; fall back only when a field is absent."""
    if longest is not None:
        return int(longest)
    if last_alive is not None:
        return int(last_alive)
    return 0


def parse_rule(text: str, fallback: str) -> str:
    """Extract a rule id from modern or legacy passports and their path."""
    patterns = [
        r"Life Passport[:\s-]*Rule\s+(\d+)",
        r"(?:Rule(?:\s+ID)?|rule_id)\s*[:=#-]?\s*\*{0,2}(\d+)\*{0,2}",
        r"rule[_\s-]*(\d+)",
        r"(?:^|[/\\])0*(\d{1,5})(?:[/\\]|$)",
    ]
    for source in (text, fallback):
        source = str(source)
        for pattern in patterns:
            m = re.search(pattern, source, re.I | re.M)
            if m:
                return m.group(1).zfill(5)
    return "unknown"

def parse_events(text: str) -> list[Event]:
    events: list[Event] = []
    for line in text.splitlines():
        if "tick **" not in line or "`" not in line:
            continue
        m = re.search(r"tick\s+\*\*(\d+)\*\*:\s*`([^`]+)`\s*-\s*(.*)$", line)
        if not m:
            continue
        tick = int(m.group(1))
        kind = m.group(2).strip()
        rest = m.group(3).strip()
        before = after = largest = None
        om = re.search(r"objects\s+(\d+)->(\d+)", rest)
        if om:
            before = int(om.group(1))
            after = int(om.group(2))
        else:
            om = re.search(r"objects=(\d+)", rest)
            if om:
                after = int(om.group(1))
        lm = re.search(r"largest=(\d+)", rest)
        if lm:
            largest = int(lm.group(1))
        events.append(Event(tick, kind, before, after, largest))
    return events


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def make_interpretation(a: PassportAnalysis) -> str:
    parts = [f"Classified as **{a.classification}** with dynamic-attractor score **{a.dynamic_attractor_score:.3f}**."]
    lifetime = observed_lifetime(a.longest_observed_age, a.last_alive_tick)
    if a.collapse_tick is None and lifetime:
        parts.append(f"It remained alive for **{lifetime:,} ticks** with no recorded collapse.")
    if a.split_birth_events or a.merge_death_events:
        parts.append(
            f"The event stream shows recurring turnover: **{a.split_birth_events}** split/birth events "
            f"and **{a.merge_death_events}** merge/death events."
        )
    if a.object_min is not None and a.object_max is not None:
        parts.append(f"Object count stayed in a bounded event range of **{a.object_min}-{a.object_max}**.")
    if (a.identity_persistence is not None and a.legacy_score is not None and a.information_survival is not None):
        if a.identity_persistence < 0.1 and a.legacy_score < 0.1 and a.information_survival < 0.1 and lifetime >= 100000:
            parts.append(
                "Important mismatch: identity/legacy/information metrics are near zero despite long visible survival. "
                "This suggests current metrics may miss dynamic morphological stability."
            )
    return " ".join(parts)


def analyze_passport(path: Path) -> PassportAnalysis:
    text = path.read_text(encoding="utf-8", errors="replace")
    events = parse_events(text)

    split_birth = [e for e in events if e.kind == "split/birth"]
    merge_death = [e for e in events if e.kind == "merge/death"]

    object_values: list[int] = []
    for e in events:
        if e.objects_before is not None:
            object_values.append(e.objects_before)
        if e.objects_after is not None:
            object_values.append(e.objects_after)
    object_min = min(object_values) if object_values else None
    object_max = max(object_values) if object_values else None
    object_range = object_max - object_min if object_min is not None and object_max is not None else None

    event_ticks = sorted(e.tick for e in events if e.kind in {"split/birth", "merge/death"})
    intervals = [b - a for a, b in zip(event_ticks, event_ticks[1:])]
    mean_interval = mean(intervals) if intervals else None
    median_interval = median(intervals) if intervals else None
    interval_std = pstdev(intervals) if len(intervals) >= 2 else None

    last_alive = grab_int(text, "- Last alive tick")
    longest = grab_int(text, "- Longest observed age")
    collapse = grab_int(text, "- Collapse tick")
    lifetime = observed_lifetime(longest, last_alive)

    long_life_score = clamp01(lifetime / 100000.0)
    turnover = len(split_birth) + len(merge_death)
    turnover_density = clamp01(turnover / max(1.0, lifetime / 2500.0)) if lifetime else 0.0
    boundedness = 0.0 if object_range is None else 1.0 - clamp01(object_range / 25.0)
    breathing_score = clamp01(0.55 * turnover_density + 0.45 * boundedness)
    turnover_balance = 0.0 if turnover == 0 else 1.0 - abs(len(split_birth) - len(merge_death)) / turnover
    no_collapse = 1.0 if collapse is None else 0.0
    dynamic_score = clamp01(0.35 * long_life_score + 0.30 * breathing_score + 0.20 * turnover_balance + 0.15 * no_collapse)

    if dynamic_score >= 0.80:
        classification = "Stable dynamic attractor"
    elif long_life_score >= 0.80 and breathing_score >= 0.55:
        classification = "Long-lived breathing scaffold"
    elif long_life_score >= 0.80:
        classification = "Long-lived stable world"
    elif breathing_score >= 0.65:
        classification = "Active bounded system"
    elif collapse is not None:
        classification = "Collapsed world"
    else:
        classification = "Unclear / weak signal"

    a = PassportAnalysis(
        file=str(path),
        rule=parse_rule(text, str(path)),
        score=grab_float(text, "- Score"),
        last_alive_tick=last_alive,
        collapse_tick=collapse,
        longest_observed_age=longest,
        peak_objects=grab_int(text, "- Peak objects"),
        peak_largest=grab_int(text, "- Peak largest object cells"),
        total_center_drift=grab_float(text, "- Total center drift"),
        final_stage=grab(text, "- Final stage"),
        identity_persistence=grab_float(text, "- Identity persistence"),
        legacy_score=grab_float(text, "- Legacy score"),
        information_survival=grab_float(text, "- Information survival"),
        events_total=len(events),
        split_birth_events=len(split_birth),
        merge_death_events=len(merge_death),
        object_min=object_min,
        object_max=object_max,
        object_range=object_range,
        mean_event_interval=mean_interval,
        median_event_interval=median_interval,
        event_interval_std=interval_std,
        breathing_score=breathing_score,
        long_life_score=long_life_score,
        turnover_balance_score=turnover_balance,
        dynamic_attractor_score=dynamic_score,
        classification=classification,
        interpretation="",
    )
    a.interpretation = make_interpretation(a)
    return a


def fmt(v, digits=3) -> str:
    if v is None:
        return "None"
    if isinstance(v, float):
        return f"{v:.{digits}f}"
    return str(v)


def render_markdown(analyses: list[PassportAnalysis]) -> str:
    lines = [
        "# Passport Analysis",
        "",
        "This report analyzes saved Life Passport markdown files and extracts long-run behavioural signals.",
        "",
        "## Summary",
        "",
        "| Rule | Lifetime | Collapse | Class | Dynamic | Breathing | Splits | Merges | Objects |",
        "| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for a in analyses:
        lifetime = observed_lifetime(a.longest_observed_age, a.last_alive_tick)
        obj = "None" if a.object_min is None else f"{a.object_min}-{a.object_max}"
        lines.append(
            f"| {a.rule} | {lifetime:,} | {a.collapse_tick if a.collapse_tick is not None else 'None'} | "
            f"{a.classification} | {a.dynamic_attractor_score:.3f} | {a.breathing_score:.3f} | "
            f"{a.split_birth_events} | {a.merge_death_events} | {obj} |"
        )
    lines.append("")

    for a in analyses:
        lifetime = observed_lifetime(a.longest_observed_age, a.last_alive_tick)
        lines.extend([
            f"## Rule {a.rule}",
            "",
            f"- Source file: `{Path(a.file).name}`",
            f"- Score: **{fmt(a.score, 6)}**",
            f"- Longest observed age: **{lifetime:,}**",
            f"- Collapse tick: **{a.collapse_tick if a.collapse_tick is not None else 'None'}**",
            f"- Classification: **{a.classification}**",
            f"- Dynamic attractor score: **{a.dynamic_attractor_score:.3f}**",
            f"- Breathing score: **{a.breathing_score:.3f}**",
            f"- Turnover balance: **{a.turnover_balance_score:.3f}**",
            f"- Split/birth events: **{a.split_birth_events}**",
            f"- Merge/death events: **{a.merge_death_events}**",
            f"- Object range: **{a.object_min}-{a.object_max}**",
            f"- Mean event interval: **{fmt(a.mean_event_interval, 1)} ticks**",
            f"- Median event interval: **{fmt(a.median_event_interval, 1)} ticks**",
            "",
            "### Interpretation",
            "",
            a.interpretation,
            "",
            "### Suggested notebook entry",
            "",
            f"- Rule {a.rule}: {a.classification}. Survived {lifetime:,} ticks; "
            f"{a.split_birth_events} split/birth and {a.merge_death_events} merge/death events. "
            "Use as evidence for dynamic morphological stability and as a target for the future Morphology Engine.",
            "",
        ])
    return "\n".join(lines)


def collect_files(input_path: Path) -> list[Path]:
    """Collect only real passport markdown files.

    Excludes generated analysis files such as passport_analysis.md.
    """
    if input_path.is_file():
        return [input_path]

    files: list[Path] = []
    for p in sorted(input_path.rglob("*passport*.md")):
        name = p.name.lower()
        if "passport_analysis" in name or name.endswith("_analysis.md"):
            continue
        files.append(p)
    return files


def eligible_passport_stems(profile_path: Path | None) -> set[str] | None:
    """Return source-passport stems in the current scientific view.

    None means that no routing file was supplied and preserves the legacy CLI.
    An empty set is a valid strict view with zero eligible passports.
    """
    if profile_path is None:
        return None
    try:
        payload = json.loads(
            profile_path.read_text(encoding="utf-8", errors="replace")
        )
    except Exception as exc:
        raise SystemExit(
            f"Invalid scientific profile routing file: {profile_path}: {exc}"
        )
    profiles = payload.get("profiles", []) if isinstance(payload, dict) else []
    if not isinstance(profiles, list):
        raise SystemExit(
            f"Invalid scientific profile routing file: {profile_path}: "
            "profiles is not a list"
        )
    return {
        Path(str(profile.get("source_file"))).stem
        for profile in profiles
        if isinstance(profile, dict)
        and profile.get("source_file")
        and profile.get("observational_eligible", True) is not False
        and str(
            profile.get(
                "evidence_channel",
                "legacy_unverified_observational",
            )
        ).lower() not in {"experimental", "perturbation", "excluded"}
    }


def filter_scientific_passports(
    files: list[Path],
    eligible_stems: set[str] | None,
) -> list[Path]:
    if eligible_stems is None:
        return files
    return [path for path in files if path.stem in eligible_stems]


def dedupe_latest_by_rule(files: list[Path]) -> tuple[list[Path], dict[str, list[Path]]]:
    """Keep only the passport with the largest observed lifetime for each rule."""
    grouped: dict[str, list[Path]] = {}
    scored: list[tuple[Path, str, int]] = []

    for p in files:
        try:
            text = read_text(p)
            rule = parse_rule(text, str(p))
            lifetime = (
                observed_lifetime(
                    grab_int(text, "- Longest observed age"),
                    grab_int(text, "- Last alive tick"),
                )
            )
        except Exception:
            rule = "unknown"
            lifetime = 0
        grouped.setdefault(rule, []).append(p)
        scored.append((p, rule, lifetime))

    best: dict[str, tuple[Path, int]] = {}
    for p, rule, lifetime in scored:
        old = best.get(rule)
        if old is None or lifetime > old[1] or (lifetime == old[1] and p.stat().st_mtime > old[0].stat().st_mtime):
            best[rule] = (p, lifetime)

    selected = sorted((v[0] for v in best.values()), key=lambda x: x.name.lower())
    duplicates = {rule: paths for rule, paths in grouped.items() if len(paths) > 1}
    return selected, duplicates


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze Universe Search Life Passport markdown files.")
    parser.add_argument("input", help="Passport markdown file or folder containing passport .md files")
    parser.add_argument("--out", default=None, help="Output markdown path")
    parser.add_argument(
        "--profiles",
        default=None,
        help=(
            "Observer Profile v31 JSON used to restrict the report to the "
            "current observational-eligible scientific view."
        ),
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    files_scanned = collect_files(input_path)
    profile_path = Path(args.profiles) if args.profiles else None
    eligible_stems = eligible_passport_stems(profile_path)
    files_all = filter_scientific_passports(files_scanned, eligible_stems)
    if not files_all:
        raise SystemExit(
            f"No scientific-view passport markdown files found in: {input_path}"
        )

    files, duplicates = dedupe_latest_by_rule(files_all)

    analyses = [analyze_passport(p) for p in files]
    md = render_markdown(analyses)

    if args.out:
        out_path = Path(args.out)
    elif input_path.is_file():
        out_path = input_path.with_name(input_path.stem + "_analysis.md")
    else:
        out_path = input_path / "passport_analysis.md"

    out_path.write_text(md, encoding="utf-8")
    duplicates_skipped = len(files_all) - len(files)
    print("")
    print("=" * 58)
    print("Universe Search Passport Analyzer")
    print("=" * 58)
    print(f"Found passport files:      {len(files_all)}")
    if eligible_stems is not None:
        print(f"Files scanned before view: {len(files_scanned)}")
        print(f"Scientific view excluded:  {len(files_scanned) - len(files_all)}")
    print(f"Unique worlds analyzed:    {len(files)}")
    print(f"Duplicates skipped:        {duplicates_skipped}")
    print(f"Report written:            {out_path}")
    print("-" * 58)

    if duplicates:
        for rule, paths in sorted(duplicates.items()):
            print(f"Rule {rule}: found {len(paths)} passports, kept longest/latest")
        print("-" * 58)

    for a in analyses:
        lifetime = observed_lifetime(a.longest_observed_age, a.last_alive_tick)
        obj = "None"
        if a.object_min is not None and a.object_max is not None:
            obj = f"{a.object_min}-{a.object_max}"
        collapse = "No" if a.collapse_tick is None else f"Yes, tick {a.collapse_tick}"

        print(f"Rule {a.rule}")
        print(f"  Lifetime:        {lifetime} ticks")
        print(f"  Classification:  {a.classification}")
        print(f"  Dynamic score:   {a.dynamic_attractor_score:.3f}")
        print(f"  Breathing score: {a.breathing_score:.3f}")
        print(f"  Collapse:        {collapse}")
        print(f"  Objects:         {obj}")
        print(f"  Events:          split/birth={a.split_birth_events}, merge/death={a.merge_death_events}")
        if a.dynamic_attractor_score >= 0.8:
            print("  Verdict:         Candidate for Morphological Stability research")
        print("-" * 58)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
