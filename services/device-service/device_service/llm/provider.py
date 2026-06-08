"""LLMProvider Protocol (ADR-009).

Every implementation's input MUST be a SanitizedSample (never a raw MQTT payload).
classify_device is async so network-bound providers do not block the FastAPI event
loop; a CPU-bound local model implementation should offload via asyncio.to_thread.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from .types import ClassificationResult, SanitizedSample


@runtime_checkable
class LLMProvider(Protocol):
    name: str  # 'anthropic' | 'openai' | 'local' | 'mock'

    async def classify_device(
        self,
        device_id: str,
        topic: str,
        sanitized: SanitizedSample,
    ) -> ClassificationResult: ...