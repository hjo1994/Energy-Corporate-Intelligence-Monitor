"""Pure normalization helpers for the raw-to-silver transform.

The source workbook mixes several encodings for the same concept across its
four business-unit sheets (consolidated into the "EliaGroup" sheet that the
raw-to-silver operator reads). These helpers make that explicit instead of
silently guessing — kept dependency-free and unit-testable on their own.
"""
from __future__ import annotations

import datetime
import logging

logger = logging.getLogger(__name__)

# "Timing start"/"Timing delivery" only ever give a quarter label; this maps
# it to that quarter's first day.
_QUARTER_START_MONTH = {"Q1": 1, "Q2": 4, "Q3": 7, "Q4": 10}

# Canonical Status values, from the Variables sheet's "Status" column
# (9 values — not just Idea/Exploration/PoC/Implementation).
_STATUS_CANONICAL = {
    "idea": "Idea",
    "exploration": "Exploration",
    "poc": "PoC",
    "mvp": "MVP",
    "production": "Production",
    "implementation": "Implementation",
    "cancelled": "Cancelled",
    "stopped": "Cancelled",  # observed in 50Hertz/IT rows; not a canonical value itself
    "on hold": "On hold",
    "unknown": "Unknown",
}

# T-shirt sizing (Variables sheet: XS, S, M, L, XL), used both for Solution
# Feasibility (effort) and, in the 50Hertz sheet only, for Value (impact) —
# same scale, different meaning.
# ASSUMPTION: larger size = larger magnitude in both cases. The Variables
# sheet documents this explicitly only for Feasibility, not for Value —
# confirm the Value direction with the Fachbereich.
_TSHIRT_SCORE = {"XS": 1.0, "S": 3.0, "M": 5.0, "L": 7.0, "XL": 9.0}

# Zero-width/invisible characters observed as copy-paste artifacts in the
# Variables sheet itself (e.g. "Connection lif﻿ecycle"), stripped only
# for catalog *matching* — never written into stored names/descriptions.
_INVISIBLE_CHARS = ("﻿", "​", "‌", "‍")


def _normalize_for_matching(text: str) -> str:
    for ch in _INVISIBLE_CHARS:
        text = text.replace(ch, "")
    return text.strip().casefold()


def normalize_status(raw_status: str | None, *, initiative_name: str) -> str:
    """Map a raw Status cell onto a canonical Variables-sheet value.

    Falls back to "Unknown" (itself a canonical value) for anything
    unrecognized — including free-text data-entry mistakes observed in the
    source (e.g. a Status cell containing a note like "In development by
    Delaware. ETA 7.2026" instead of picking a dropdown value) — logging the
    original text so it can be fixed at the source rather than silently
    miscategorized.
    """
    if not raw_status or not raw_status.strip():
        return "Unknown"
    key = raw_status.strip().lower()
    mapped = _STATUS_CANONICAL.get(key)
    if mapped is None:
        logger.warning(
            "Unrecognized Status %r for initiative %r - mapped to 'Unknown'",
            raw_status,
            initiative_name,
        )
        return "Unknown"
    return mapped


def tshirt_to_score(size: str | None) -> float | None:
    if not size or not str(size).strip():
        return None
    return _TSHIRT_SCORE.get(str(size).strip().upper())


def derive_solution_complexity_score(solution_feasibility, complexity) -> float | None:
    """Initiative.solution_complexity_score: 50Hertz/IT/Corporate use the
    Feasibility T-shirt size; ETB instead gives a direct 1-10 Complexity
    number. The two fields never co-occur per row in the source data, so
    prefer whichever is present and fall back to None (never fabricate a
    value).
    """
    score = tshirt_to_score(solution_feasibility)
    if score is not None:
        return score
    if complexity is not None:
        return float(complexity)
    return None


def derive_value_score(raw_value) -> float | None:
    """Initiative.value_score: 50Hertz encodes it as a T-shirt size, ETB as
    a direct 1-10 number, IT and Corporate & OneSAP+ do not track it at all
    in the source (stays None — never fabricated as a placeholder).

    The source column mixes both encodings, so a dataframe reader that
    infers a single dtype for the whole column (e.g. Polars, when some
    rows are "M" and others "9") hands the ETB numbers to us as numeric
    strings rather than ints/floats — handled explicitly below rather than
    silently losing them to the T-shirt lookup.
    """
    if raw_value is None:
        return None
    if isinstance(raw_value, bool):
        return None
    if isinstance(raw_value, (int, float)):
        return float(raw_value)
    if isinstance(raw_value, str):
        text = raw_value.strip()
        try:
            return float(text)
        except ValueError:
            return tshirt_to_score(text)
    return None


def derive_timing_date(
    raw_timing, *, assumed_year: int, initiative_name: str, field_label: str
) -> datetime.datetime | None:
    """Best-effort conversion of a 'Timing start'/'Timing delivery' cell
    into a date.

    ASSUMPTION, needs Fachbereich confirmation: the source never gives a
    real date — almost always a bare quarter label ("Q1".."Q4"), and in
    some rows (8 at the time of writing) the bare year "2027" with no quarter at all. There is
    nothing in the data to tell us which calendar year a quarter label
    refers to, so we assume `assumed_year` (the workbook's own planning
    year) for every quarter-only value; a bare year is taken as 1 January
    of that year. This is a coarse placeholder for planning purposes, not a
    committed date — in particular it will be wrong for any initiative
    whose quarter actually falls in a year other than `assumed_year` (the
    "2027" delivery values are a concrete sign such initiatives exist).
    """
    if raw_timing is None:
        return None
    text = str(raw_timing).strip().upper()
    if not text:
        return None
    if text in _QUARTER_START_MONTH:
        return datetime.datetime(assumed_year, _QUARTER_START_MONTH[text], 1)
    if text.isdigit() and len(text) == 4:
        return datetime.datetime(int(text), 1, 1)
    logger.warning(
        "Unrecognized %s value %r for initiative %r - left as NULL",
        field_label,
        raw_timing,
        initiative_name,
    )
    return None


def match_catalog_name(
    raw_text: str | None,
    *,
    canonical_names_by_match_key: dict[str, str],
    initiative_name: str,
    field_label: str,
) -> str | None:
    """Match a raw cell value against a reference/lookup catalog's canonical
    names (SolutionType from "Solution Type", ValueType from "Flagship"),
    ignoring case and copy-paste-artifact invisible characters.

    Returns the catalog's own spelling of the matched name (never the raw
    text) so the FK always points at the seeded canonical row, or None
    (logged) when the raw text does not match any canonical entry — e.g.
    free-text solution descriptions instead of a picked category, confirmed
    to be the majority case for "Solution Type".
    """
    if not raw_text or not raw_text.strip():
        return None
    match = canonical_names_by_match_key.get(_normalize_for_matching(raw_text))
    if match is None:
        logger.warning(
            "%s value %r for initiative %r does not match any catalog entry - FK left as NULL",
            field_label,
            raw_text,
            initiative_name,
        )
        return None
    return match


def build_match_key_index(canonical_names: list[str]) -> dict[str, str]:
    """Build the {normalized_key: canonical_name} index `match_catalog_name`
    expects, from a catalog's list of canonical names as read from the
    Variables sheet.
    """
    return {_normalize_for_matching(name): name for name in canonical_names}
