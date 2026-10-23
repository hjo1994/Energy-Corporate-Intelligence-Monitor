"""The two hashes behind the silver upsert (SHA-256, hex).

The source sheets carry no initiative ID ("Number" is a row-number formula
that changes whenever rows are sorted, inserted or deleted), so silver needs
its own notion of "the same initiative":

- key_hash (identity): business unit + normalized, casefolded name. Same key
  in a later load -> update candidate; unknown key -> new initiative. A real
  rename therefore counts as "old one gone (deactivated), new one inserted".
- row_hash (delta): over the source columns that flow into silver. Same key
  and same row_hash -> unchanged, nothing is written.

Normalization for both: trim, collapse whitespace including non-breaking
spaces, drop zero-width characters, NULL -> "", parts joined with \\x1f.
"""
from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence

from ai_cockpit_ingestion.transforms.normalize import _INVISIBLE_CHARS, clean_text

SEPARATOR = "\x1f"

# Source columns that flow into silver, in hash order. A column a sheet does
# not have is left out for that sheet (see row_hash_columns). Not hashed on
# purpose: Number (row-number formula), Strategic Link, Strategic Link ETB,
# Impediments, 2026, Kolom1 and the load/ID columns.
ROW_HASH_COLUMNS = (
    "Name",
    "Description",
    "Owner",
    "Department",
    "Flagship",
    "AI Layer",
    "Status",
    "Solution Type",
    "Solution Feasibility",
    "High-Level Cost Assessment",
    "Expected Outcome",
    "Added Value",
    "Value",
    "Complexity",
    "Timing start",
    "Timing delivery",
)


def normalize(value) -> str:
    text = clean_text(value) or ""
    for ch in _INVISIBLE_CHARS:
        text = text.replace(ch, "")
    return text


def _sha256(parts: Sequence[str]) -> str:
    return hashlib.sha256(SEPARATOR.join(parts).encode("utf-8")).hexdigest()


def key_hash(business_unit: str, name) -> str:
    return _sha256([business_unit, normalize(name).casefold()])


def row_hash_columns(sheet_columns: Sequence[str]) -> tuple[str, ...]:
    return tuple(c for c in ROW_HASH_COLUMNS if c in sheet_columns)


def row_hash(row: Mapping[str, object], columns: Sequence[str]) -> str:
    return _sha256([normalize(row.get(c)) for c in columns])
