"""Helpers for deriving a child's effective age from persisted birth data."""

from __future__ import annotations

from datetime import date


def infer_birth_year_from_age(
    age: int,
    *,
    as_of: date | None = None,
) -> tuple[int, int | None]:
    """Infer an approximate birth year from a legacy integer age input.

    Month is intentionally left unknown because the current client only collects
    age, not a birthday. This still allows age to increase automatically over
    time, albeit with month-level uncertainty until a month is provided later.
    """
    effective_date = as_of or date.today()
    return effective_date.year - age, None


def calculate_child_age(
    *,
    stored_age: int,
    birth_year: int | None,
    birth_month: int | None,
    as_of: date | None = None,
) -> int:
    """Return the effective age to use across APIs and business logic."""
    if birth_year is None:
        return stored_age

    effective_date = as_of or date.today()
    age = effective_date.year - birth_year

    if birth_month is not None and effective_date.month < birth_month:
        age -= 1

    return max(age, 0)