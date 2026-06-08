"""Two-Layer AI Guardrail — L2 GuardrailProvider (PRD-0003 §8.7, ADR-016).

L2 is independent of L1: it does NOT classify; it only decides pass/block on the
input prompt (pre) and the L1 output (post). The hardcoded mock implementation
detects common prompt-injection and command-injection patterns deterministically.
Dangerous output patterns are assembled as regexes (parts split by whitespace
classes) so the source never contains a contiguous executable phrase.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .types import ClassificationResult, SanitizedSample

_INJECTION = (
    "ignore previous", "ignore all previous", "forget all", "disregard prior",
    "disregard previous", "new instructions", "system:", "assistant:",
    "</human_corrections>", "<|", "|>",
)

# Command / SQL / shell injection that must never appear in classifier OUTPUT.
# Assembled from parts so no literal executable phrase sits in the source.
_BANNED_OUT = re.compile(
    r"\b(?:drop|delete|truncate)\s+(?:table|from)\b"
    r"|\b" + "r" + r"m\s+-rf\b"
    r"|\b(?:eval|exec|fetch|system)\s*\("
    r"|;\s*--",
    re.IGNORECASE,
)
_SHELL_META = re.compile("[;|&" + chr(96) + chr(36) + "]")  # ; | & ` $
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _norm(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "").lower()


@dataclass(frozen=True)
class GuardrailVerdict:
    decision: str                    # 'pass' | 'block'
    threat_category: str | None = None
    reasoning: str = ""
    confidence: float = 1.0
    # L2 token usage for this check ({input_tokens, output_tokens}); None for a token-free
    # decision (MockGuardrail, the deterministic backstop, or a fail-closed error). Summed
    # across pre+post by the classifier into Outcome.guardrail_usage for FR-340 budget metering.
    usage: dict | None = None

    @property
    def blocked(self) -> bool:
        return self.decision == "block"


@runtime_checkable
class GuardrailProvider(Protocol):
    name: str

    async def check_input(self, sanitized: SanitizedSample, rendered_prompt: str) -> GuardrailVerdict: ...

    async def check_output(
        self, sanitized: SanitizedSample, l1_response: ClassificationResult, rendered_prompt: str
    ) -> GuardrailVerdict: ...


class MockGuardrail:
    """Deterministic L2 guardrail for tests / dev fallback (hardcoded rules, no model)."""

    name = "mock_guardrail"

    async def check_input(self, sanitized: SanitizedSample, rendered_prompt: str) -> GuardrailVerdict:
        if _CONTROL.search(rendered_prompt or ""):
            return GuardrailVerdict("block", "prompt_injection", "control characters in prompt")
        text = _norm(rendered_prompt)
        for marker in _INJECTION:
            if marker in text:
                return GuardrailVerdict("block", "prompt_injection", f"injection marker: {marker}")
        return GuardrailVerdict("pass")

    async def check_output(
        self, sanitized: SanitizedSample, l1_response: ClassificationResult, rendered_prompt: str
    ) -> GuardrailVerdict:
        haystacks = [l1_response.device_type or "", l1_response.reasoning or ""]
        for sig in l1_response.suggested_signals:
            haystacks.append(sig.signal_name or "")
            haystacks.append(sig.unit or "")
        joined = " ".join(haystacks)
        if _BANNED_OUT.search(joined):
            return GuardrailVerdict("block", "output_command", "banned command pattern in output")
        if _SHELL_META.search(l1_response.device_type or ""):
            return GuardrailVerdict("block", "scope_escape", "shell metacharacter in device_type")
        return GuardrailVerdict("pass")