"""Pure extraction of related scientific report lines."""
from __future__ import annotations

import re


def load_optional_lines(
    text: str,
    heading: str,
    rule: str | None = None,
    limit: int = 5,
) -> list[str]:
    if not text:
        return []
    lines: list[str] = []
    if heading == "questions":
        for line in text.splitlines():
            if line.startswith("| ★") or line.startswith("| *"):
                parts = [part.strip() for part in line.strip("|").split("|")]
                if (
                    len(parts) >= 3
                    and parts[2] != "Question"
                    and (not rule or rule in parts[1])
                ):
                    lines.append(parts[2])
            if len(lines) >= limit:
                break
    elif heading == "discoveries":
        source_lines = text.splitlines()
        for index, line in enumerate(source_lines):
            match = re.match(r"###\s+(D\d+):\s+(.+)", line)
            if match:
                context = " ".join(source_lines[index:index + 8])
                if not rule or re.search(
                    rf"(?<!\d){re.escape(rule)}(?!\d)", context
                ):
                    lines.append(f"{match.group(1)}: {match.group(2)}")
            if len(lines) >= limit:
                break
    elif heading == "mechanisms":
        for line in text.splitlines():
            match = re.match(r"###\s+(M-\d+):\s+(.+)", line)
            if match:
                lines.append(f"{match.group(1)}: {match.group(2)}")
            if len(lines) >= limit:
                break
    elif heading == "principles":
        for line in text.splitlines():
            match = re.match(r"###\s+(GP-[^:]+):\s+(.+)", line)
            if match:
                lines.append(f"{match.group(1)}: {match.group(2)}")
            if len(lines) >= limit:
                break
    elif heading == "predictions":
        for line in text.splitlines():
            match = re.match(r"###\s+(P-\d+):\s+(.+)", line)
            if match:
                lines.append(f"{match.group(1)}: {match.group(2)}")
            if len(lines) >= limit:
                break
    return lines


__all__ = ["load_optional_lines"]
