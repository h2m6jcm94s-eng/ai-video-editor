# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"""Output guardrails using llm-guard scanners.

Runs on AI model responses before they reach the user.
Fail-open on scanner initialization errors.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class OutputCheckResult:
    allowed: bool
    reason: Optional[str] = None
    flagged_categories: List[str] = None
    confidence: float = 1.0

    def __post_init__(self):
        if self.flagged_categories is None:
            self.flagged_categories = []


# Lazy-loaded scanner instances (module-level singleton pattern)
_scanners: Optional[List] = None


def _get_scanners() -> List:
    """Initialize llm-guard output scanners lazily."""
    global _scanners
    if _scanners is not None:
        return _scanners

    try:
        from llm_guard.output_scanners import Toxicity, Secrets, Sensitive, MaliciousURLs

        _scanners = [
            Toxicity(threshold=0.7),
            Secrets(),
            Sensitive(),
            MaliciousURLs(threshold=0.7),
        ]
        logger.info("llm-guard output scanners initialized (Toxicity, Secrets, Sensitive, MaliciousURLs)")
        return _scanners
    except ImportError:
        logger.warning("llm-guard not installed; output guardrails disabled")
        _scanners = []
        return _scanners
    except Exception as e:
        logger.error("Failed to initialize llm-guard output scanners: %s", e)
        _scanners = []
        return _scanners


def evaluate_output(text: str) -> OutputCheckResult:
    """Evaluate AI response text for toxic, leaked secrets, sensitive data, or malicious URLs.

    Args:
        text: The AI model's response text.

    Returns:
        OutputCheckResult: allowed=True if safe, allowed=False with reason/categories if blocked.
    """
    scanners = _get_scanners()
    if not scanners:
        # Fail-open if scanners couldn't load
        return OutputCheckResult(allowed=True)

    flagged: List[str] = []
    max_risk = 0.0

    # Run each scanner individually so we can collect all flagged categories
    for scanner in scanners:
        try:
            # Output scanners accept (prompt, output) — pass empty prompt per spec
            _sanitized, is_valid, risk_score = scanner.scan("", text)
            if not is_valid:
                scanner_name = scanner.__class__.__name__
                flagged.append(scanner_name.lower())
                if risk_score > max_risk:
                    max_risk = risk_score
        except Exception as e:
            # Individual scanner failure is logged but doesn't fail-open the whole check
            logger.warning("Scanner %s failed: %s", scanner.__class__.__name__, e)

    if flagged:
        return OutputCheckResult(
            allowed=False,
            reason=f"Output blocked by guardrails: {', '.join(flagged)}",
            flagged_categories=flagged,
            confidence=min(1.0, max_risk),
        )

    return OutputCheckResult(allowed=True)
