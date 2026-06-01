"""Correction → prompt-context assembly (PRD-0003 §8.6.4 / §8.6.5a, FR-331).

Turns relevant device_corrections rows into de-sanitised CorrectionContext objects
and enforces the 32KB prompt-size circuit breaker by LRU-dropping the oldest
corrections until the rendered user_message fits. Pure / synchronous so it is fully
unit-testable; DB retrieval and applied_count bookkeeping live in the caller.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace

from .llm.prompt import render_sample
from .llm.types import CorrectionContext, SanitizedSample

PROMPT_SIZE_CAP_BYTES = 32 * 1024  # §8.6.5a hard cap on the serialized user_message
_EXPLANATION_MAX = 500             # mirrors §7.3a length ceiling (defence-in-depth)

# device_type "family" grouping (§8.6.4 #3). No synonym taxonomy is defined yet, so a
# type is its own family; centralised here so widening it later is a one-place change.
DEVICE_TYPE_FAMILIES: dict[str, tuple[str, ...]] = {}


def device_type_family(device_type: str | None) -> tuple[str, ...]:
    if not device_type:
        return ()
    return DEVICE_TYPE_FAMILIES.get(device_type, (device_type,))


def topic_prefix(topic: str | None) -> str:
    """First two `/`-separated segments (e.g. 'ems/factory'). '' unless BOTH of the
    first two segments are non-empty — so 'ems/' or '/x' do not produce a matchable
    prefix (would otherwise match stray rows in retrieve_relevant)."""
    parts = (topic or "").split("/")
    if len(parts) >= 2 and parts[0] and parts[1]:
        return f"{parts[0]}/{parts[1]}"
    return ""


def build_context(row: dict) -> CorrectionContext:
    created = row.get("created_at")
    return CorrectionContext(
        verdict=row["verdict"],
        corrected_device_type=row.get("corrected_device_type"),
        explanation_truncated=(row.get("human_explanation") or "")[:_EXPLANATION_MAX],
        created_at_iso=created.isoformat() if created is not None else "",
    )


def cap_to_prompt_size(
    base: SanitizedSample,
    contexts: Sequence[CorrectionContext],
    *,
    cap_bytes: int = PROMPT_SIZE_CAP_BYTES,
    render: Callable[[SanitizedSample], str] = render_sample,
) -> tuple[tuple[CorrectionContext, ...], bool]:
    """Keep the largest PREFIX of `contexts` (ordered most-recent-first) whose rendered
    user_message fits under cap_bytes; the dropped tail is the oldest corrections.
    Returns (kept, truncated). Kept is always a prefix, so the caller maps kept→row ids
    by position. FR-331 sets no count limit, so the only bound is this byte cap.

    Rendered size is monotonic non-decreasing in the prefix length, so we binary-search
    the boundary — O(log n) renders rather than O(n) (a device can accumulate unbounded
    corrections over time)."""
    n = len(contexts)

    def _fits(k: int) -> bool:
        candidate = replace(base, human_corrections=tuple(contexts[:k]))
        return len(render(candidate).encode("utf-8")) <= cap_bytes

    if n == 0 or _fits(n):
        return tuple(contexts), False
    # n does not fit -> find the largest k in [0, n) that does (monotonic predicate)
    best, lo, hi = 0, 0, n
    while lo <= hi:
        mid = (lo + hi) // 2
        if _fits(mid):
            best, lo = mid, mid + 1
        else:
            hi = mid - 1
    return tuple(contexts[:best]), True
