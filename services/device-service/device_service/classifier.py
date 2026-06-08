"""Classification pipeline (PRD-0003 §4 / §8.6 / §8.7, FR-302/303/304/312/316/317/332/336/337).

Orchestrates one candidate classification:
  sanitize (caller) -> budget gate -> L2 pre -> L1 (retry) -> L2 post ->
  output validator -> correction-conflict -> confidence threshold -> digest.

Pure orchestration: collaborators (L1 provider, L2 guardrail) are injected; the DB
(advisory lock, status write, digest persistence) is handled by the caller (subscriber)
using the returned Outcome. Any failure path produces a deterministic system_fallback
result + digest so a digest is ALWAYS available (FR-317), and never auto-confirms.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace

from .digest import build_fallback_digest, build_llm_digest
from .llm.guardrail import GuardrailProvider
from .llm.prompt import render_sample
from .llm.provider import LLMProvider
from .llm.types import ClassificationResult, ProviderError, SanitizedSample, SignalSuggestion
from .output_validator import validate

CONFIDENCE_THRESHOLD = 0.9
DEFAULT_RETRIES = 3
# guardrail reasoning is stored in the audit detail; cap it so a future LLM-based guardrail
# can't echo a large attacker-controlled payload into the audit row (sec-review LOW-1).
_MAX_REASON_LEN = 200


def signal_shape_hash(sanitized: SanitizedSample) -> str:
    shape = sorted((f.field_name, f.datatype) for f in sanitized.fields)
    return hashlib.sha256(repr(shape).encode()).hexdigest()


def cache_key(sanitized: SanitizedSample, provider: str, model: str, prompt_version: str) -> str:
    raw = "|".join([sanitized.device_id, sanitized.topic, signal_shape_hash(sanitized),
                    provider, model, prompt_version])
    return hashlib.sha256(raw.encode()).hexdigest()


@dataclass(frozen=True)
class GuardrailBlock:
    """L2 guardrail BLOCK details for the audit trail (FR-339 / §8.7.5). Hashes fingerprint
    the L1 input/output for correlation without persisting their content."""
    phase: str                       # 'pre' | 'post'
    threat_category: str | None
    reasoning: str
    l1_input_hash: str
    l1_output_hash: str | None = None


def _sha(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _output_fingerprint(result: ClassificationResult) -> str:
    sigs = sorted((s.signal_name, s.unit, s.datatype, s.direction) for s in result.suggested_signals)
    return _sha(f"{result.device_type}|{round(result.confidence, 4)}|{result.reasoning}|{sigs}")


@dataclass(frozen=True)
class Outcome:
    result: ClassificationResult
    digest: dict
    summary_source: str          # 'llm' | 'system_fallback'
    new_status: str              # 'confirmed' | 'candidate'
    correction_conflict: bool
    last_error: str | None
    from_cache: bool = False
    guardrail_block: GuardrailBlock | None = None   # set only when L2 BLOCKED (FR-339 audit)
    # L2 token usage actually consumed THIS classification (pre + post), for FR-340 budget
    # settle. {input_tokens, output_tokens}; zeros when the guardrail is free (mock / backstop)
    # or did not run. On a cache hit this carries the original call's usage — the budget settle
    # must ignore it when from_cache is True (no tokens were spent this time).
    guardrail_usage: dict | None = None


class Classifier:
    def __init__(
        self, provider: LLMProvider, guardrail: GuardrailProvider, *,
        model: str = "", prompt_version: str = "v1",
        confidence_threshold: float = CONFIDENCE_THRESHOLD, retries: int = DEFAULT_RETRIES,
        cache_max: int = 4096,
    ):
        self._provider = provider
        self._guardrail = guardrail
        self._model = model
        self._prompt_version = prompt_version
        self._threshold = confidence_threshold
        self._retries = retries
        self._cache_max = cache_max
        self._cache: dict[str, Outcome] = {}

    def _fallback(
        self, sanitized: SanitizedSample, default_device_type: str, *,
        first_seen_at: str, generated_at: str, last_error: str,
        guardrail_block: GuardrailBlock | None = None, guardrail_usage: dict | None = None,
    ) -> Outcome:
        signals = tuple(
            SignalSuggestion(f.field_name, "", "", "read") for f in sanitized.fields
        )
        result = ClassificationResult(default_device_type, signals, 0.0, "LLM 不可用，請人工判斷", {})
        digest = build_fallback_digest(
            sanitized, default_device_type,
            first_seen_at=first_seen_at, generated_at=generated_at, prompt_version=self._prompt_version,
        )
        # fallback never caches (transient) and never auto-confirms. guardrail_usage still carries
        # any L2 tokens spent before the block (e.g. a pre-check that ran the model then blocked).
        return Outcome(result, digest, "system_fallback", "candidate", False, last_error,
                       guardrail_block=guardrail_block, guardrail_usage=guardrail_usage)

    async def classify(
        self, sanitized: SanitizedSample, *, budget_ok: bool = True, guardrail_ok: bool = True,
        default_device_type: str = "unknown", latest_correction_device_type: str | None = None,
        first_seen_at: str = "", generated_at: str = "", force: bool = False,
    ) -> Outcome:
        # Cache is reused ONLY for clean, context-free, same-shape classifications.
        # Any security-relevant context (human corrections, correction-conflict context,
        # budget block, or force) bypasses the cache entirely so the gates always run —
        # FR-316 (token saving) must never defeat FR-329 budget / FR-332 conflict / §8.7 guardrail.
        cacheable = (
            not force and budget_ok
            and not sanitized.human_corrections
            and latest_correction_device_type is None
        )
        key = cache_key(sanitized, self._provider.name, self._model, self._prompt_version)
        if cacheable and key in self._cache:                       # FR-316
            return replace(self._cache[key], from_cache=True)

        rendered = render_sample(sanitized)
        # accumulate L2 token usage across the pre + post checks (FR-340). fb snapshots whatever
        # has been spent so far, so a pre-check that ran the model then blocked is still metered.
        g_usage = {"input_tokens": 0, "output_tokens": 0}

        def _meter(verdict) -> None:
            if verdict is not None and verdict.usage is not None:
                g_usage["input_tokens"] += int(verdict.usage.get("input_tokens", 0))
                g_usage["output_tokens"] += int(verdict.usage.get("output_tokens", 0))

        fb = lambda err, gb=None: self._fallback(                   # noqa: E731
            sanitized, default_device_type,
            first_seen_at=first_seen_at, generated_at=generated_at, last_error=err,
            guardrail_block=gb, guardrail_usage=dict(g_usage))

        if not budget_ok:                                          # FR-329
            return fb("budget_exhausted")
        if not guardrail_ok:                                       # FR-340: L2 budget exhausted ->
            return fb("guardrail_budget_exhausted")                # L1 ALSO stops, all fallback

        pre = await self._guardrail.check_input(sanitized, rendered)   # FR-336
        _meter(pre)
        if pre.blocked:
            return fb("guardrail_blocked_input", GuardrailBlock(   # FR-339 audit: pre-check, no L1 output
                "pre", pre.threat_category, pre.reasoning[:_MAX_REASON_LEN], _sha(rendered)))

        result = None
        for _ in range(self._retries):                             # FR-312
            try:
                result = await self._provider.classify_device(sanitized.device_id, sanitized.topic, sanitized)
                break
            except ProviderError:
                continue
        if result is None:
            return fb("llm_failed_after_retries")

        post = await self._guardrail.check_output(sanitized, result, rendered)   # FR-337
        _meter(post)
        if post.blocked:
            return fb("guardrail_blocked_output", GuardrailBlock(  # FR-339 audit: post-check, L1 ran
                "post", post.threat_category, post.reasoning[:_MAX_REASON_LEN],
                _sha(rendered), _output_fingerprint(result)))

        ok, reason, cleaned = validate(result)                     # FR-333
        if not ok:
            return fb(reason or "output_validator_rejected")

        conflict = bool(                                           # FR-332
            latest_correction_device_type
            and cleaned.device_type != latest_correction_device_type
        )
        new_status = (
            "confirmed" if (not conflict and cleaned.confidence > self._threshold) else "candidate"
        )
        digest = build_llm_digest(
            sanitized, cleaned, provider=self._provider.name, model=self._model,
            first_seen_at=first_seen_at, generated_at=generated_at, prompt_version=self._prompt_version,
        )
        outcome = Outcome(cleaned, digest, "llm", new_status, conflict, None,
                          guardrail_usage=dict(g_usage))
        if cacheable:  # only clean, context-free results are cached (see above)
            if len(self._cache) >= self._cache_max:
                self._cache.pop(next(iter(self._cache)))  # bound memory: drop oldest entry
            self._cache[key] = outcome
        return outcome