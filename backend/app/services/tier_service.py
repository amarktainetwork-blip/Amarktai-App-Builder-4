"""Quality tier normalization for backend runtime decisions.

The public product now exposes only Standard and Premium. Older project records
may still contain cheap/balanced, so backend code must accept those values while
persisting and reporting canonical tiers.
"""
from __future__ import annotations

from typing import Any


STANDARD = "standard"
PREMIUM = "premium"
PUBLIC_TIERS = (STANDARD, PREMIUM)
LEGACY_TIER_MAP = {
    "cheap": STANDARD,
    "balanced": STANDARD,
    "standard": STANDARD,
    "premium": PREMIUM,
}


def normalize_quality_tier(value: Any, *, default: str = STANDARD) -> str:
    """Return canonical public tier: ``standard`` or ``premium``."""
    raw = str(value or default).strip().lower()
    return LEGACY_TIER_MAP.get(raw, default if default in PUBLIC_TIERS else STANDARD)


def is_premium(value: Any) -> bool:
    return normalize_quality_tier(value) == PREMIUM


def repair_attempt_limit(value: Any) -> int:
    return 3 if is_premium(value) else 2


def tier_description(value: Any) -> str:
    tier = normalize_quality_tier(value)
    if tier == PREMIUM:
        return "Best available models, deeper reasoning, richer media, stronger QA."
    return "Fast, capable generation using efficient high-quality models."
