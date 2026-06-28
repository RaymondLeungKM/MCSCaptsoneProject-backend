"""
Privacy gate utility for cohort-based analytics.

Enforces:
- parent consent for analytics
- minimum cohort size (k-anonymity baseline)
- standardized suppression payload
"""
from __future__ import annotations

from dataclasses import dataclass

from app.models.user import User


DEFAULT_MINIMUM_COHORT_THRESHOLD = 1


@dataclass
class PrivacyGateResult:
    allowed: bool
    is_suppressed: bool
    reason: str | None
    minimum_cohort_threshold: int


def evaluate_privacy_gate(
    *,
    user: User,
    cohort_size: int,
    minimum_cohort_threshold: int = DEFAULT_MINIMUM_COHORT_THRESHOLD,
) -> PrivacyGateResult:
    if not user.consent_analytics:
        return PrivacyGateResult(
            allowed=False,
            is_suppressed=True,
            reason="analytics_consent_disabled",
            minimum_cohort_threshold=minimum_cohort_threshold,
        )

    return PrivacyGateResult(
        allowed=True,
        is_suppressed=False,
        reason=None,
        minimum_cohort_threshold=minimum_cohort_threshold,
    )


def suppression_payload(result: PrivacyGateResult) -> dict[str, object]:
    return {
        "is_suppressed": result.is_suppressed,
        "reason": result.reason,
        "minimum_cohort_threshold": result.minimum_cohort_threshold,
    }