"""Canonical rule identifiers used by the discovery slice."""
from __future__ import annotations

import re
from typing import Any


_CONTEXT_PATTERNS = (
    re.compile(r"(?i)\brule[_\-\s:]*0*(\d{1,5})\b"),
    re.compile(r"(?i)\br[_\-\s:]*0*(\d{1,5})\b"),
)
_EXACT_NUMERIC_PATTERN = re.compile(r"^0*(\d{1,5})$")
_STANDALONE_FIVE_DIGIT_PATTERN = re.compile(r"(?<!\d)(\d{5})(?!\d)")


def normalize_rule_id(value: Any) -> str | None:
    """Return a canonical five-digit rule id without accepting dates."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    exact = _EXACT_NUMERIC_PATTERN.fullmatch(text)
    if exact:
        return exact.group(1).zfill(5)
    for pattern in _CONTEXT_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1).zfill(5)
    standalone = _STANDALONE_FIVE_DIGIT_PATTERN.search(text)
    return standalone.group(1) if standalone else None
