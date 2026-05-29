"""Output validator (FR-333, ADR-009).

Runs on the LLM response before it is written to the DB. On rejection the caller
must fall back to system_fallback (and NOT count budget — see ADR-014).
Checks:
  1. reasoning truncated to <= 500 chars.
  2. reject if blacklist words appear (password/token/api_key/secret/credential).
  3. reject if device_type / signal_name / unit contain unsafe chars (SQL/shell
     injection reflected in the output).
"""
from __future__ import annotations

import re
from dataclasses import replace

from .llm.types import ClassificationResult

MAX_REASONING = 500
BLACKLIST = ("password", "token", "api_key", "secret", "credential")
# allowed chars for classification names / units (letters, digits, space, _-/.%° )
_SAFE = re.compile(r"^[A-Za-z0-9 _\-/.%°]+$")


def _has_blacklist(text: str | None) -> bool:
    low = (text or "").lower()
    return any(b in low for b in BLACKLIST)


def validate(result: ClassificationResult) -> tuple[bool, str | None, ClassificationResult]:
    """Return (ok, reason, cleaned_result). ok=False -> use system_fallback."""
    if _has_blacklist(result.reasoning):
        return False, "blacklist_word_in_reasoning", result
    if not result.device_type or not _SAFE.match(result.device_type):
        return False, "unsafe_device_type", result
    for sig in result.suggested_signals:
        if not sig.signal_name or not _SAFE.match(sig.signal_name):
            return False, "unsafe_signal_name", result
        if sig.unit and not _SAFE.match(sig.unit):
            return False, "unsafe_signal_unit", result
        if _has_blacklist(sig.signal_name) or _has_blacklist(sig.unit):
            return False, "blacklist_word_in_signal", result

    cleaned = replace(result, reasoning=(result.reasoning or "")[:MAX_REASONING])
    return True, None, cleaned