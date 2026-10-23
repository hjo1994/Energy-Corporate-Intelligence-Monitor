"""Values derived from the stored Initiative columns.

Not part of the data model (the pipeline only stores the inputs), so they
are computed here — once as SQL expressions for sorting/aggregating, once in
Python for the response. Both follow the input-orchestration value heuristic:

- hypothetical value = sum of the four value buckets (EUR per year)
- potential value    = hypothetical value x confidence x delivery (EUR per year)
- annual cost        = one-time costs / depreciation years + operating costs

A missing input makes the derived value NULL instead of silently counting as 0.
"""
from __future__ import annotations

from sqlalchemy import ColumnElement, case

from app.models import Initiative

_BUCKETS = (
    Initiative.efficiency_score_eur,
    Initiative.quality_score_eur,
    Initiative.risk_reduction_score_eur,
    Initiative.strategic_value_score_eur,
)

hypothetical_value_sql: ColumnElement = _BUCKETS[0] + _BUCKETS[1] + _BUCKETS[2] + _BUCKETS[3]
potential_value_sql: ColumnElement = (
    hypothetical_value_sql * Initiative.confidence_score * Initiative.delivery_score
)
annual_cost_sql: ColumnElement = (
    case(
        (Initiative.depreciation_years > 0, Initiative.one_time_costs * 1.0 / Initiative.depreciation_years),
        else_=None,
    )
    + Initiative.operating_costs
)


def hypothetical_value(i: Initiative) -> float | None:
    buckets = (
        i.efficiency_score_eur,
        i.quality_score_eur,
        i.risk_reduction_score_eur,
        i.strategic_value_score_eur,
    )
    return None if any(b is None for b in buckets) else sum(buckets)


def potential_value(i: Initiative) -> float | None:
    hypothetical = hypothetical_value(i)
    if hypothetical is None or i.confidence_score is None or i.delivery_score is None:
        return None
    return hypothetical * i.confidence_score * i.delivery_score


def annual_cost(i: Initiative) -> float | None:
    if i.one_time_costs is None or not i.depreciation_years or i.operating_costs is None:
        return None
    return i.one_time_costs / i.depreciation_years + i.operating_costs
