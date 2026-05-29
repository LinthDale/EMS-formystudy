"""LLMProvider Protocol (ADR-009).

Every implementation MUST take a SanitizedSample as input — never a raw MQTT
payload string / dict. Sanitisation happens in the service layer (sanitizer.py).
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from .types import ClassificationResult, SanitizedSample


@runtime_checkable
class LLMProvider(Protocol):
    name: str  # 'anthropic' | 'openai' | 'local' | 'mock'

    def classify_device(
        self,
        device_id: str,
        topic: str,
        sanitized: SanitizedSample,
    ) -> ClassificationResult: ...