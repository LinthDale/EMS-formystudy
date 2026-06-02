"""MCP tool implementations (PRD-0003 §8.2, ADR-012) — transport-agnostic.

The AI channel gets exactly three tools: read low-confidence candidates, read one digest,
and re-classify with a hint. NO confirm/override/reject (those are human/OPS REST actions,
§8.6.7). These are plain async functions over (db, classifier, settings); the MCP server
(slice 1b-ii) wraps them with auth / rate-limit / audit. Keeping them here makes the tool
logic unit-testable without the Streamable-HTTP transport.
"""
from __future__ import annotations

from .correction_validator import CorrectionRejected, validate_correction_text
from .discovery_pipeline import reclassify_device
from .repositories import digest_repo

LOW_CONFIDENCE_THRESHOLD = 0.9   # FR-303 / §8.2: candidates at/below this need human-ish review
HINT_MAX_LEN = 500


class ToolError(Exception):
    """Tool-level error the MCP layer maps to an error result. `code` is a stable token."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


async def list_low_confidence_candidates(db, *, limit: int = 20) -> list[dict]:
    """§8.2: digests of candidate devices with ai_confidence <= 0.9 (lowest first). Read via
    the AI pool (AI role has SELECT on devices + device_review_digests)."""
    async with db.ai_pool.acquire() as conn:
        return await digest_repo.list_low_confidence(
            conn, threshold=LOW_CONFIDENCE_THRESHOLD, limit=limit)


async def get_device_digest(db, *, device_id: str) -> dict:
    """§8.2: single human-review digest. Raises ToolError('not_found') if absent."""
    async with db.ai_pool.acquire() as conn:
        digest = await digest_repo.get(conn, device_id)
    if digest is None:
        raise ToolError("not_found", f"no review digest for device {device_id!r}")
    return digest


async def classify_with_context(db, classifier, settings, *, device_id: str, hint: str) -> dict:
    """§8.2: re-run classification for a CANDIDATE device with a human hint, forcing a fresh
    LLM call (FR-316 cache miss) and still passing the budget gate (FR-329). The hint enters
    the prompt, so it is validated (§7.3a injection/structural/secret/format rules; length
    1-500). Returns the resulting digest. Raises ToolError if the hint is rejected or the
    device cannot be re-classified (unknown / not a candidate / no samples)."""
    try:
        clean_hint = validate_correction_text(hint, min_len=1, max_len=HINT_MAX_LEN)
    except CorrectionRejected as exc:
        raise ToolError("invalid_hint", f"hint rejected: {exc.reason}") from exc
    outcome = await reclassify_device(
        db, classifier, settings, device_id=device_id, force=True, hint=clean_hint)
    if outcome is None:
        raise ToolError(
            "not_reclassifiable",
            f"device {device_id!r} could not be re-classified (unknown, not a candidate, "
            "or no recent samples — demote_to_candidate first if it is confirmed)")
    return outcome.digest
