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


def signal_shape_hash(sanitized: SanitizedSample) -> str:
    shape = sorted((f.field_name, f.datatype) for f in sanitized.fields)
    return hashlib.sha256(repr(shape).encode()).hexdigest()


def cache_key(sanitized: SanitizedSample, provider: str, model: str, prompt_version: str) -> str:
    raw = "|".join([sanitized.device_id, sanitized.topic, signal_shape_hash(sanitized),
                    provider, model, prompt_version])
    return hashlib.sha256(raw.encode()).hexdigest()


@dataclass(frozen=True)
class Outcome:
    result: ClassificationResult
    digest: dict
    summary_source: str          # 'llm' | 'system_fallback'
    new_status: str              # 'confirmed' | 'candidate'
    correction_conflict: bool
    last_error: str | None
    from_cache: bool = False


class Classifier:
    def __init__(
        self, provider: LLMProvider, guardrail: GuardrailProvider, *,
        model: str = "", prompt_version: str = "v1",
        confidence_threshold: float = CONFIDENCE_THRESHOLD, retries: int = DEFAULT_RETRIES,
    ):
        self._provider = provider
        self._guardrail = guardrail
        self._model = model
        self._prompt_version = prompt_version
        self._threshold = confidence_threshold
        self._retries = retries
        self._cache: dict[str, Outcome] = {}

    def _fallback(
        self, sanitized: SanitizedSample, default_device_type: str, *,
        first_seen_at: str, generated_at: str, last_error: str,
    ) -> Outcome:
        signals = tuple(
            SignalSuggestion(f.field_name, "", "", "read") for f in sanitized.fields
        )
        result = ClassificationResult(default_device_type, signals, 0.0, "LLM 不可用，請人工判斷", {})
        digest = build_fallback_digest(
            sanitized, default_device_type,
            first_seen_at=first_seen_at, generated_at=generated_at, prompt_version=self._prompt_version,
        )
        # fallback never caches (transient) and never auto-confirms
        return Outcome(result, digest, "system_fallback", "candidate", False, last_error)

    async def classify(
        self, sanitized: SanitizedSample, *, budget_ok: bool = True,
        default_device_type: str = "unknown", latest_correction_device_type: str | None = None,
        first_seen_at: str = "", generated_at: str = "", force: bool = False,
    ) -> Outcome:
        key = cache_key(sanitized, self._provider.name, self._model, self._prompt_version)
        if not force and key in self._cache:                       # FR-316
            return replace(self._cache[key], from_cache=True)

        rendered = render_sample(sanitized)
        fb = lambda err: self._fallback(                            # noqa: E731
            sanitized, default_device_type,
            first_seen_at=first_seen_at, generated_at=generated_at, last_error=err)

        if not budget_ok:                                          # FR-329
            return fb("budget_exhausted")

        pre = await self._guardrail.check_input(sanitized, rendered)   # FR-336
        if pre.blocked:
            return fb("guardrail_blocked_input")

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
        if post.blocked:
            return fb("guardrail_blocked_output")

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
        outcome = Outcome(cleaned, digest, "llm", new_status, conflict, None)
        self._cache[key] = outcome
        return outcome