"""Output validator (FR-333, ADR-009).

Runs on the LLM response before it is written to the DB. On rejection the caller
must fall back to system_fallback (and NOT count budget — see ADR-014).
Checks:
  1. blacklist words anywhere in reasoning or device_type (NFKC-normalised,
     zero-width-stripped — defeats full-width / zero-width evasion).
  2. confidence within [0.0, 1.0].
  3. device_type / signal_name non-empty (not whitespace-only) and safe chars.
  4. signal unit safe chars (units may start with % or ° so they keep the
     permissive set; identifiers must not be whitespace-only).
  5. reasoning truncated to <= 500 chars.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import replace

from .llm.types import ClassificationResult

MAX_REASONING = 500
BLACKLIST = ("password", "token", "api_key", "secret", "credential")
# allowed chars for classification names / units (letters, digits, space, _-/.%° )
_SAFE = re.compile(r"^[A-Za-z0-9 _\-/.%°]+$")
_ZERO_WIDTH = re.compile("[" + "".join(chr(c) for c in (0x200b, 0x200c, 0x200d, 0x200e, 0x200f, 0x2060, 0xfeff)) + "]")


def _has_blacklist(text: str | None) -> bool:
    normalized = unicodedata.normalize("NFKC", text or "")
    cleaned = _ZERO_WIDTH.sub("", normalized).lower()
    return any(b in cleaned for b in BLACKLIST)


def _bad_identifier(value: str | None) -> bool:
    """True if value is empty / whitespace-only / contains unsafe chars."""
    return not value or not value.strip() or not _SAFE.match(value)


def validate(result: ClassificationResult) -> tuple[bool, str | None, ClassificationResult]:
    """Return (ok, reason, cleaned_result). ok=False -> use system_fallback."""
    if _has_blacklist(result.reasoning):
        return False, "blacklist_word_in_reasoning", result
    if _has_blacklist(result.device_type):
        return False, "blacklist_word_in_device_type", result
    if not (0.0 <= result.confidence <= 1.0):
        return False, "confidence_out_of_range", result
    if _bad_identifier(result.device_type):
        return False, "unsafe_device_type", result
    for sig in result.suggested_signals:
        if _bad_identifier(sig.signal_name):
            return False, "unsafe_signal_name", result
        if sig.unit and not _SAFE.match(sig.unit):
            return False, "unsafe_signal_unit", result
        if _has_blacklist(sig.signal_name) or _has_blacklist(sig.unit):
            return False, "blacklist_word_in_signal", result

    cleaned = replace(result, reasoning=(result.reasoning or "")[:MAX_REASONING])
    return True, None, cleaned