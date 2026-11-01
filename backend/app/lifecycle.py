"""Stage gates and the value domains of form 1.

Stage gates: a use case has one date per gate (Needs, Scope, Deploy, Retire).
A date up to today means the gate is passed, a later date means it is planned.
Which gates must lie in the past for a stage comes from the form 2 Excel
("20261028 form 2 data fields", Sheet1, gate date rows): "scope gate must be
passed before PoC, deploy gate must be passed before production". From that:

- Idea, Exploration:           scope and deploy gate not passed yet (planned or empty)
- PoC, MVP, Implementation:    scope gate passed; deploy gate not passed yet
- Production, Retired:         scope and deploy gate passed
- On hold, Cancelled, Unknown: no rule

The Excel has no rule for the needs and the retire gate. Dates that are set
must be in gate order (Needs <= Scope <= Deploy <= Retire).

Value domains: every number of form 1 is chosen from a short list of ranges;
the API stores the range's representative value (like the running costs).
"""
from __future__ import annotations

import datetime

from app.models import GATE_DATE_FIELDS

GATES = tuple(GATE_DATE_FIELDS)

_EARLY = ((), ("Scope", "Deploy"))
_BUILDING = (("Scope",), ("Deploy",))
_LIVE = (("Scope", "Deploy"), ())
# stage -> (gates that must be passed, gates that must not be passed yet)
STAGE_GATE_RULES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "Idea": _EARLY, "Exploration": _EARLY,
    "PoC": _BUILDING, "MVP": _BUILDING, "Implementation": _BUILDING,
    "Production": _LIVE, "Retired": _LIVE,
}


def _day(value: datetime.date | datetime.datetime | None) -> datetime.date | None:
    if isinstance(value, datetime.datetime):
        return value.date()
    return value


def gate_dates(state: dict) -> dict[str, datetime.date | None]:
    """Gate -> date (as a date) from a state or record dict with the *_gate_date fields."""
    return {gate: _day(state.get(field)) for gate, field in GATE_DATE_FIELDS.items()}


def last_passed_gate(state: dict, today: datetime.date) -> str | None:
    """The latest gate in gate order whose date is up to today."""
    passed = [gate for gate, day in gate_dates(state).items() if day is not None and day <= today]
    return passed[-1] if passed else None


def stage_problems(stage: str | None, dates: dict[str, datetime.date | None], today: datetime.date) -> list[str]:
    """What does not fit between the stage and the gate dates (empty: all fine)."""
    problems = []
    must_pass, not_yet = STAGE_GATE_RULES.get(stage or "", ((), ()))
    for gate in must_pass:
        day = dates.get(gate)
        if day is None:
            problems.append(f"Stage {stage} needs the date the {gate.lower()} gate was passed.")
        elif day > today:
            problems.append(f"Stage {stage} needs the {gate.lower()} gate to be passed: its date must not be in the future.")
    for gate in not_yet:
        day = dates.get(gate)
        if day is not None and day <= today:
            problems.append(f"In stage {stage} the {gate.lower()} gate is not passed yet: its date must be in the future.")
    set_dates = [(gate, day) for gate, day in dates.items() if day is not None]
    for (gate_a, day_a), (gate_b, day_b) in zip(set_dates, set_dates[1:]):
        if day_b < day_a:
            problems.append(f"The {gate_b.lower()} gate cannot come before the {gate_a.lower()} gate.")
    return problems


# ---------- value domains of form 1 ----------

_SHARES = ((0.1, "about 10 %"), (0.25, "about 25 %"), (0.5, "about 50 %"), (0.75, "about 75 %"), (0.9, "about 90 %"))
_EVENT_COSTS = ((5_000, "under 10k €"), (30_000, "10k–50k €"), (150_000, "50k–250k €"), (500_000, "over 250k €"))

# field -> ((stored value, label), ...), smallest first
VALUE_DOMAINS: dict[str, tuple[tuple[float, str], ...]] = {
    "cases_per_year": ((50, "under 100"), (500, "100–1,000"), (5_000, "1,000–10,000"), (50_000, "10,000–100,000"),
                       (150_000, "over 100,000")),
    "hours_saved_per_case": ((0.1, "under 15 min"), (0.4, "15–30 min"), (0.75, "30–60 min"), (2.5, "1–4 h"),
                             (6, "over 4 h")),
    "error_rate_before": ((0.01, "under 2 %"), (0.035, "2–5 %"), (0.075, "5–10 %"), (0.15, "10–20 %"),
                          (0.3, "over 20 %")),
    "errors_avoided": _SHARES,
    "cost_per_error": ((50, "under 100 €"), (500, "100–1k €"), (5_000, "1k–10k €"), (25_000, "over 10k €")),
    "risk_events_per_year": ((0.5, "less than 1"), (3, "1–5"), (12, "5–20"), (40, "more than 20")),
    "events_avoided": _SHARES,
    "cost_per_event": _EVENT_COSTS,
    "delay_events_per_year": ((3, "under 5"), (12, "5–20"), (60, "20–100"), (150, "over 100")),
    "cost_of_delay_per_event": _EVENT_COSTS,
    "lead_time_saved": _SHARES,
    "one_time_costs": ((25_000, "under 50k €"), (75_000, "50k–100k €"), (175_000, "100k–250k €"),
                       (500_000, "250k €–1M €"), (1_500_000, "over 1M €")),
}


def domain_problems(values: dict) -> list[str]:
    """Numbers that are not one of the values of their domain (unset fields are skipped)."""
    problems = []
    for field, domain in VALUE_DOMAINS.items():
        value = values.get(field)
        if value is not None and not any(abs(value - v) < 1e-9 for v, _ in domain):
            allowed = ", ".join(f"{v:g} ({label})" for v, label in domain)
            problems.append(f"{field}: choose one of {allowed}")
    return problems
