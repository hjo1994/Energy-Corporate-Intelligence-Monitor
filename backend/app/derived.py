"""Values derived from the stored silver Initiative columns.

Not part of the data model, so they are computed here — once as SQL
expressions for sorting/aggregating, once in Python for the response:

- hypothetical value = sum of the four value buckets (EUR per year)
- annual cost        = one-time costs / depreciation years + running costs
                       (stored as expected costs, i.e. already weighted by delivery;
                       cost if delivered = annual cost / delivery)

The potential value, the realized value and the risk level come from gold
(AssessedInitiatives); before a use case is assessed the API shows a
provisional potential computed like gold does (provisional_potential).

A missing input makes the derived value NULL instead of silently counting as 0.
"""
from __future__ import annotations

from sqlalchemy import ColumnElement, case

from app.models import Initiative

_BUCKET_NAMES = ("efficiency_score_eur", "quality_score_eur", "risk_reduction_score_eur", "strategic_value_score_eur")
_BUCKETS = tuple(getattr(Initiative, n) for n in _BUCKET_NAMES)

hypothetical_value_sql: ColumnElement = _BUCKETS[0] + _BUCKETS[1] + _BUCKETS[2] + _BUCKETS[3]
annual_cost_sql: ColumnElement = (
    case(
        (Initiative.depreciation_years > 0, Initiative.one_time_costs * 1.0 / Initiative.depreciation_years),
        else_=None,
    )
    + Initiative.running_costs
)


def _get(i, name):
    return i.get(name) if isinstance(i, dict) else getattr(i, name, None)


def hypothetical_value(i) -> float | None:
    buckets = [_get(i, n) for n in _BUCKET_NAMES]
    return None if any(b is None for b in buckets) else sum(buckets)


def provisional_potential(i) -> float | None:
    """Same formula as gold: sum of the buckets x confidence x delivery."""
    hypothetical = hypothetical_value(i)
    confidence, delivery = _get(i, "confidence_score"), _get(i, "delivery_score")
    if hypothetical is None or confidence is None or delivery is None:
        return None
    return hypothetical * confidence * delivery


def annual_cost(i) -> float | None:
    one_time, years, running = _get(i, "one_time_costs"), _get(i, "depreciation_years"), _get(i, "running_costs")
    if one_time is None or not years or running is None:
        return None
    return one_time / years + running
