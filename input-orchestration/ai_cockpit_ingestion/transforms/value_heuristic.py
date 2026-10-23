"""Value/cost ESTIMATE per initiative ("Heuristik v2: Buckets einzeln") —
agreed in thread "Nutzen-Quantifizierung", ported from data/value_heuristic.py.

Each of the four value buckets is computed with its own value-sizing formula
from drivers derived from existing source attributes; the hypothetical value
is then simply their sum (deterministic, nothing estimated top-down):

- Value score (T-shirt or 1-10)      -> reach: cases/events per year
- Solution type family               -> effect per case (hours saved, errors
                                        avoided, risk reduction, speed-up)
- Flagship                           -> cost of an error / event / delay
- AI Layer and free-text keywords    -> which buckets apply at all

Confidence comes from the status, Delivery from feasibility/complexity
(else solution type), costs from the cost assessment (else feasibility, else
solution type). All amounts are EUR per year except OneTimeCosts.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

HOURLY_RATE_EUR = 60

SIZES = ("XS", "S", "M", "L", "XL")
VOLUME = {"XS": 200, "S": 1_000, "M": 3_000, "L": 8_000, "XL": 20_000}  # cases per year (reach)
EVENTS = {"XS": 2, "S": 5, "M": 10, "L": 20, "XL": 40}  # delay-relevant events per year

# Effect per case, by solution type family.
HOURS_SAVED = {"assistant": 0.25, "rpa": 0.5, "genai_process": 1.0, "ml": 0.5}
ERROR_RATE_BEFORE = 0.08
ERROR_CUT = {"assistant": 0.25, "rpa": 0.6, "genai_process": 0.4, "ml": 0.5}  # share of errors avoided
RISK_SHARE = 0.1  # risk-bearing share of cases
P_EVENT_BEFORE = 0.02
P_EVENT_CUT = {"assistant": 0.1, "rpa": 0.4, "genai_process": 0.2, "ml": 0.3}
SPEEDUP = {"assistant": 0.05, "rpa": 0.1, "genai_process": 0.15, "ml": 0.1}  # share of lead time saved

# Cost of an error / risk event / delay, by flagship ("-" = none/unknown).
COST_ERROR = {
    "CAPEX delivery": 2000, "Grid planning process": 2000, "System Operations process": 1500,
    "Connection lifecycle": 1000, "Corporate processes": 300, "Software Development lifecycle": 500, "-": 500,
}
COST_EVENT = {
    "System Operations process": 100_000, "CAPEX delivery": 50_000, "Grid planning process": 50_000,
    "Connection lifecycle": 20_000, "Corporate processes": 20_000, "Software Development lifecycle": 10_000,
    "-": 20_000,
}
COST_DELAY = {
    "CAPEX delivery": 100_000, "Grid planning process": 100_000, "Connection lifecycle": 50_000,
    "System Operations process": 50_000, "Corporate processes": 20_000, "Software Development lifecycle": 20_000,
    "-": 20_000,
}
STRATEGIC_FLAGSHIPS = ("CAPEX delivery", "Grid planning process", "Connection lifecycle")

KW_QUALITY = r"error|quality|consisten|accura|rework|check|verif|complian"
KW_RISK = r"risk|complian|safety|outage|failure|incident|security|fraud|alarm|audit"
KW_STRATEGIC = r"faster|speed|time.to.market|delay|lead time|accelerat|planning"

CONFIDENCE_FACTOR = {"Low": 0.35, "Medium": 0.60, "High": 0.80}
DELIVERY_FACTOR = {"Low": 0.40, "Medium": 0.65, "High": 0.90}
DELIVERY_BY_SOLUTION_TYPE = {
    "Copilot": "High", "General chatbot": "High", "Github co-pilot": "High",
    "Rule based automation on cloud": "High", "Rule based automation on prem": "High",
    "Custom chatbot": "Medium", "Copilot agent": "Medium", "Custom LLM integration": "Medium",
    "Custom agent": "Medium", "Custom AI/ML integration": "Medium", "Custom AI/ML model": "Low",
}
COST_SIZE_BY_SOLUTION_TYPE = {
    "Copilot": "XS", "General chatbot": "XS", "Github co-pilot": "XS",
    "Rule based automation on cloud": "S", "Rule based automation on prem": "S", "Custom chatbot": "S",
    "Copilot agent": "S", "Custom LLM integration": "M", "Custom agent": "M",
    "Custom AI/ML integration": "M", "Custom AI/ML model": "M",
}
COST_EUR = {"XS": 25_000, "S": 75_000, "M": 200_000, "L": 500_000, "XL": 1_000_000}
# Some feasibility cells hold the Variables sheet's explanation text instead of the size.
FEASIBILITY_FROM_TEXT = (("All required capabilities", "XS"), ("Most capabilities", "S"), ("Core capabilities", "M"))
LICENSE_SOLUTION_TYPES = ("Copilot", "General chatbot", "Github co-pilot")  # written off in 1 year


@dataclass
class ValueEstimate:
    efficiency_eur: float
    quality_eur: float
    risk_reduction_eur: float
    strategic_eur: float
    confidence_level: str
    confidence_score: float
    delivery_level: str
    delivery_score: float
    one_time_costs: float
    operating_costs: float
    depreciation_years: int
    rationale: list[str] = field(default_factory=list)

    @property
    def hypothesized_eur(self) -> float:
        return self.efficiency_eur + self.quality_eur + self.risk_reduction_eur + self.strategic_eur


def _s(value) -> str:
    return str(value).strip() if value is not None else ""


def _tshirt(value: str) -> str | None:
    value = value.strip().upper()
    if value in SIZES:
        return value
    match = re.match(r"^(XS|S|M|L|XL)\b", value)
    return match.group(1) if match else None


def _number_to_size(number: str) -> str:
    n = float(number)
    return "XS" if n <= 2 else "S" if n <= 4 else "M" if n <= 6 else "L" if n <= 8 else "XL"


def solution_family(solution_type: str, text: str) -> str:
    if solution_type in ("Copilot", "General chatbot", "Github co-pilot", "Custom chatbot"):
        return "assistant"
    if solution_type.startswith("Rule based"):
        return "rpa"
    if solution_type in ("Custom LLM integration", "Custom agent", "Copilot agent"):
        return "genai_process"
    if solution_type.startswith("Custom AI/ML"):
        return "ml"
    # Free-text solution type (the majority): derive the family from the text.
    if re.search(r"forecast|predict|optimi|model|anomal", text):
        return "ml"
    if re.search(r"chatbot|assistant|copilot", text):
        return "assistant"
    return "genai_process"


def estimate_value(
    *,
    status: str | None,
    value: str | None,
    ai_layer: str | None,
    solution_type: str | None,
    flagship: str | None,
    solution_feasibility: str | None,
    complexity: str | None,
    cost_assessment: str | None,
    description: str | None,
    expected_outcome: str | None,
    added_value: str | None,
) -> ValueEstimate:
    """All inputs are the raw (bronze) cell texts; `solution_type`/`flagship`
    should already be matched to the catalog spelling where possible.
    """
    status_l = _s(status).lower()
    value_s = _s(value)
    solution_type = _s(solution_type)
    text = " ".join(_s(t) for t in (description, expected_outcome, added_value)).lower()
    notes: list[str] = []

    # 1. Drivers
    size = _tshirt(value_s) if value_s else None
    if not size and re.fullmatch(r"\d+(\.\d+)?", value_s):
        size = _number_to_size(value_s)
    layer_raw = _s(ai_layer).lower()
    layer = (
        "prod" if "productivity" in layer_raw
        else "bpa" if "automation" in layer_raw
        else "ops" if "operational" in layer_raw
        else None
    )
    if size:
        notes.append(f"Reach from Value {value_s} -> {size}")
    else:
        size = "M" if layer == "bpa" else "S"
        notes.append(f"No Value score: reach {size} from AI Layer")
    family = solution_family(solution_type, text)
    fl = _s(flagship).replace("﻿", "")
    fl = fl if fl in COST_DELAY else "-"
    volume = VOLUME[size]

    # 2. Buckets, each with its own value-sizing formula.
    # Efficiency: volume x hours saved per case x hourly rate
    efficiency = volume * HOURS_SAVED[family] * HOURLY_RATE_EUR
    explicit = None
    match = re.search(r"(\d[\d.,]*)\s*(k|tsd|eur|€)", text)
    if match and "eur" in text:
        amount = float(match.group(1).replace(".", "").replace(",", ""))
        if match.group(2) == "k":
            amount *= 1000
        if amount >= 10_000:
            efficiency = explicit = amount
            notes.append(f"Efficiency = explicit amount in text {int(amount)} EUR")
    # Quality: volume x cost per error x (error rate before - after)
    quality = 0.0
    if layer == "bpa" or re.search(KW_QUALITY, text):
        quality = volume * COST_ERROR[fl] * ERROR_RATE_BEFORE * ERROR_CUT[family]
        notes.append("Quality applies")
    # Risk reduction: risk-bearing cases x cost of event x (p before - p after)
    risk_reduction = 0.0
    if layer == "ops" or re.search(KW_RISK, text):
        risk_reduction = volume * RISK_SHARE * COST_EVENT[fl] * P_EVENT_BEFORE * P_EVENT_CUT[family]
        notes.append("Risk reduction applies")
    # Strategic: events x cost of delay x lead time saved
    strategic = 0.0
    if fl in STRATEGIC_FLAGSHIPS or re.search(KW_STRATEGIC, text):
        strategic = EVENTS[size] * COST_DELAY[fl] * SPEEDUP[family]
        notes.append("Strategic applies")
    notes.append(f"Family {family}, flagship {fl}")
    efficiency, quality, risk_reduction, strategic = (
        round(x, -3) for x in (efficiency, quality, risk_reduction, strategic)
    )

    # 3. Confidence
    if "production" in status_l or status_l in ("mvp", "implementation"):
        confidence = "Medium"
    else:
        confidence = "Low"
    if explicit and confidence == "Low":
        confidence = "Medium"
    if value_s == "" and confidence == "Medium" and "production" not in status_l:
        confidence = "Low"

    # 4. Delivery
    feasibility_raw = _s(solution_feasibility)
    feasibility = _tshirt(feasibility_raw) or next(
        (size_ for prefix, size_ in FEASIBILITY_FROM_TEXT if feasibility_raw.startswith(prefix)), None
    )
    complexity_s = _s(complexity)
    if feasibility:
        delivery = {"XS": "High", "S": "High", "M": "Medium", "L": "Low", "XL": "Low"}[feasibility]
        notes.append(f"Delivery from feasibility {feasibility}")
    elif re.fullmatch(r"\d+", complexity_s):
        c = int(complexity_s)
        delivery = "High" if c <= 3 else "Medium" if c <= 6 else "Low"
        notes.append(f"Delivery from complexity {c}")
    elif solution_type in DELIVERY_BY_SOLUTION_TYPE:
        delivery = DELIVERY_BY_SOLUTION_TYPE[solution_type]
        notes.append("Delivery from solution type")
    else:
        delivery = "Medium"
        notes.append("Delivery default Medium")
    if "production" in status_l:
        delivery = "High"

    # 5. Costs
    cost_raw = _s(cost_assessment)
    cost_size = _tshirt(cost_raw) if cost_raw else None
    if cost_size:
        notes.append(f"Cost from cost assessment {cost_size}")
    elif feasibility:
        cost_size = feasibility
        notes.append("Cost from feasibility size")
    elif solution_type in COST_SIZE_BY_SOLUTION_TYPE:
        cost_size = COST_SIZE_BY_SOLUTION_TYPE[solution_type]
        notes.append("Cost from solution type")
    else:
        cost_size = "S"
        notes.append("Cost default S")
    one_time = COST_EUR[cost_size]
    if cost_raw.lower().startswith(("already funded", "cost are part", "initial costs are covered")):
        notes.append("Funded elsewhere")
    if solution_type in LICENSE_SOLUTION_TYPES:
        years = 1
    elif re.search(r"platform|infrastructure|plattform", text):
        years = 5
    else:
        years = 3
    operating = round(one_time * 0.25, -3)

    return ValueEstimate(
        efficiency_eur=efficiency,
        quality_eur=quality,
        risk_reduction_eur=risk_reduction,
        strategic_eur=strategic,
        confidence_level=confidence,
        confidence_score=CONFIDENCE_FACTOR[confidence],
        delivery_level=delivery,
        delivery_score=DELIVERY_FACTOR[delivery],
        one_time_costs=float(one_time),
        operating_costs=float(operating),
        depreciation_years=years,
        rationale=notes,
    )
