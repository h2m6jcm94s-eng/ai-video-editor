# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"""Guardrails evaluation engine.

Tries to use NeMo Guardrails when available, falls back to heuristic checks.
"""

import re
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ─── Prompt Injection Patterns ──────────────────────────────────────────────

INJECTION_PATTERNS = [
    # Classic ignore/override patterns
    r"ignore\s+(all\s+)?(previous\s+)?instructions",
    r"ignore\s+(the\s+)?(above\s+)?(prompt|system\s+message|context)",
    r"disregard\s+(all\s+)?(previous\s+)?instructions",
    r"forget\s+(all\s+)?(previous\s+)?(instructions|prompts|context)",
    r"override\s+(all\s+)?(previous\s+)?instructions",
    r"you\s+are\s+now\s+",
    r"new\s+instructions?:",
    r"system\s+prompt\s*:",
    r"\{\{\.?System\s*\}\}",
    r"<\|im_start\|>system",
    r"<\|system\|>",
    r"\[\s*SYSTEM\s*\]",
    r"\[\s*INSTRUCTION\s*\]",
    r"role\s*:\s*system",
    r"from\s+now\s+on\s*,?\s*you\s+are",
    r"let's\s+play\s+a\s+game",
    r"pretend\s+you\s+are\s+an?\s+(unrestricted|uncensored|jailbroken)",
    r"DAN\s*\(Do\s+Anything\s+Now\)",
    r"jailbreak",
    r"developer\s+mode",
    r"sudo\s+",
    r"root\s+access",
]

# ─── PII Patterns ───────────────────────────────────────────────────────────

PII_PATTERNS = [
    (r"\b\d{3}-\d{2}-\d{4}\b", "ssn"),  # SSN
    (r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b", "credit_card"),  # Credit card
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "email"),  # Email
    (r"\b\d{3}-\d{3}-\d{4}\b", "phone_us"),  # US phone
    (r"\b\+?\d[\d\s-]{8,}\d\b", "phone_intl"),  # International phone
]

# ─── Toxicity / Adult Keywords (simple heuristic) ───────────────────────────

TOXICITY_KEYWORDS = [
    "kill yourself", "suicide", "die in", "hope you die",
    "racist", "nazi", "hitler", "white supremacist",
]

# ─── Data Classes ───────────────────────────────────────────────────────────


@dataclass
class GuardrailResult:
    allowed: bool
    reason: Optional[str] = None
    flagged_categories: List[str] = None
    confidence: float = 1.0

    def __post_init__(self):
        if self.flagged_categories is None:
            self.flagged_categories = []


# ─── Heuristic Engine ───────────────────────────────────────────────────────


class HeuristicGuardrails:
    """Fallback guardrails using regex and heuristic checks."""

    def evaluate(self, text: str) -> GuardrailResult:
        text_lower = text.lower()
        flagged: List[str] = []

        # Check prompt injection
        for pattern in INJECTION_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                flagged.append("prompt_injection")
                break

        # Check PII
        for pattern, category in PII_PATTERNS:
            if re.search(pattern, text):
                flagged.append(f"pii:{category}")

        # Check toxicity
        for keyword in TOXICITY_KEYWORDS:
            if keyword in text_lower:
                flagged.append("toxicity")
                break

        # Length check (basic anti-DOS)
        if len(text) > 10000:
            flagged.append("input_too_long")

        if flagged:
            return GuardrailResult(
                allowed=False,
                reason=f"Blocked categories: {', '.join(flagged)}",
                flagged_categories=flagged,
            )

        return GuardrailResult(allowed=True)


# ─── NeMo Guardrails Engine ─────────────────────────────────────────────────


class NeMoGuardrails:
    """Wrapper around NVIDIA NeMo Guardrails when available."""

    def __init__(self) -> None:
        self._engine: Optional[Any] = None
        self._load()

    def _load(self) -> None:
        try:
            from nemoguardrails import RailsConfig, LLMRails

            config_path = Path(__file__).parent / "config"
            if config_path.exists():
                self._config = RailsConfig.from_path(str(config_path))
                self._engine = LLMRails(self._config)
                logger.info("NeMo Guardrails loaded successfully")
            else:
                logger.warning("NeMo Guardrails config not found at %s", config_path)
        except ImportError:
            logger.warning("nemoguardrails not installed, falling back to heuristics")
        except Exception as e:
            logger.error("Failed to load NeMo Guardrails: %s", e)

    def evaluate(self, text: str) -> GuardrailResult:
        if self._engine is None:
            # Fall back to heuristics
            return HeuristicGuardrails().evaluate(text)

        try:
            # NeMo Guardrails evaluation
            response = self._engine.generate(
                messages=[{"role": "user", "content": text}]
            )
            # Check if the response was blocked
            if response.get("blocked"):
                return GuardrailResult(
                    allowed=False,
                    reason=response.get("explanation", "Blocked by guardrails"),
                    flagged_categories=response.get("flagged_categories", ["blocked"]),
                )
            return GuardrailResult(allowed=True)
        except Exception as e:
            logger.error("NeMo Guardrails evaluation error: %s", e)
            # Fail-open: fallback to heuristics
            return HeuristicGuardrails().evaluate(text)


# ─── Unified Engine ─────────────────────────────────────────────────────────


class GuardrailsEngine:
    """Unified guardrails engine that picks the best available backend."""

    def __init__(self) -> None:
        self._nemo: Optional[NeMoGuardrails] = None
        self._heuristic = HeuristicGuardrails()
        self._try_nemo()

    def _try_nemo(self) -> None:
        try:
            self._nemo = NeMoGuardrails()
        except Exception as e:
            logger.warning("Could not initialize NeMo Guardrails: %s", e)

    def evaluate(self, text: str) -> GuardrailResult:
        if self._nemo is not None and self._nemo._engine is not None:
            return self._nemo.evaluate(text)
        return self._heuristic.evaluate(text)


# Lazy singleton
_engine: Optional[GuardrailsEngine] = None


def get_engine() -> GuardrailsEngine:
    global _engine
    if _engine is None:
        _engine = GuardrailsEngine()
    return _engine
