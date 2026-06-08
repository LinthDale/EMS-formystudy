"""Human correction-text validation (PRD-0003 §7.3a, FR-330/341 — S2 / WARN-1).

Applied identically to `human_explanation` and `deactivation_reason` (§7.3a). This
is defence-in-depth ahead of the DB length CHECK and ahead of the L2 guardrail:
a human correction is later injected into the L1 prompt, so its free text is an
injection surface.

Order (PRD §7.3a):
  0. NFKC-normalize first  (so fullwidth ＜＞｛｝ cannot bypass the char rules)
  1. length 30-500 on the NORMALIZED text
  2. reject control chars  (\\x00-\\x1f except \\n / \\t, plus \\x7f)
  2b. reject Unicode format chars (category Cf: ZWSP/ZWJ/RTL-override/soft-hyphen/
      BOM/…). NFKC does NOT fold these, \\s does NOT match them, and they are outside
      the control range — so without this rule an attacker could split a blocked
      phrase ("ig<ZWSP>nore previous") or smuggle an RTL override into the persisted
      text. Rejecting (not stripping) keeps the stored value faithful and the error
      explicit. (security review H-1 / M-1)
  3. reject structural chars  < > { } \\ `  (fullwidth already folded by NFKC)
  4. reject secret blacklist words  (case-insensitive)
  5. reject prompt-injection phrases  (whitespace-insensitive)

Returns the normalized text (the value to persist); raises CorrectionRejected with
a stable machine `reason` on the first violation.
"""
from __future__ import annotations

import re
import unicodedata

MIN_LEN = 30
MAX_LEN = 500

# control chars except \n (0x0a) and \t (0x09); include DEL (0x7f)
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_STRUCTURAL_CHARS = frozenset("<>{}\\`")
_SECRET_WORDS = ("password", "token", "api_key", "apikey", "secret", "credential")
# whitespace-insensitive injection phrases (matched on casefolded, ws-collapsed text)
_INJECTION_PHRASES = (
    "ignore previous", "ignore prior", "forget all", "forget everything",
    "disregard prior", "disregard previous", "new instructions",
    "system:", "assistant:",
)


class CorrectionRejected(ValueError):
    """Raised when correction text fails a §7.3a rule. `reason` is a stable token
    (length / control_char / structural_char / secret_blacklist / injection)."""

    def __init__(self, reason: str, detail: str = ""):
        self.reason = reason
        super().__init__(f"{reason}: {detail}" if detail else reason)


def validate_correction_text(raw: str, *, min_len: int = MIN_LEN, max_len: int = MAX_LEN) -> str:
    """§7.3a content validation. Default length 30-500 (human_explanation / deactivation_reason).
    min_len is relaxable for shorter free text that still must pass the injection/structural/
    secret/format checks — e.g. an MCP classify_with_context `hint` (min_len=1)."""
    text = unicodedata.normalize("NFKC", raw or "")          # (0)

    if not (min_len <= len(text) <= max_len):                # (1)
        raise CorrectionRejected("length", f"{len(text)} chars (allowed {min_len}-{max_len})")

    if _CONTROL_RE.search(text):                             # (2)
        raise CorrectionRejected("control_char")

    if any(unicodedata.category(c) == "Cf" for c in text):   # (2b) format chars
        raise CorrectionRejected("format_char")

    bad = _STRUCTURAL_CHARS & set(text)                      # (3)
    if bad:
        raise CorrectionRejected("structural_char", "".join(sorted(bad)))

    folded = text.casefold()
    for word in _SECRET_WORDS:                               # (4)
        if word in folded:
            raise CorrectionRejected("secret_blacklist", word)

    collapsed = re.sub(r"\s+", " ", folded)                  # (5)
    for phrase in _INJECTION_PHRASES:
        if phrase in collapsed:
            raise CorrectionRejected("injection", phrase)

    return text
