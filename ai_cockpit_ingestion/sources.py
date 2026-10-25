"""The four raw source sheets and their extract (bronze) tables.

Single source of truth for both DAGs: RawToBronze creates one load task per
entry, and the BronzeToSilver meta DAG renders one DAG per entry from its
template. Column lists are the sheets' own headers, 1:1 and in sheet order,
exactly as in `solution documentation/Logical Data Model.drawio`
("Extrakte: Rohdaten je Quellblatt").

The sheets share most column names but not all of them: Value only exists
in 50Hertz and ETB, Complexity and the Timing columns only in ETB, Added
Value not in 50Hertz. The silver transform reads columns by name and treats
a missing column as empty, so no per-source mapping code is needed.
"""
from __future__ import annotations

from dataclasses import dataclass


SHEET = "sheet"  # a raw sheet: snapshot loads, one business unit, soft delete
USER_INPUT = "user_input"  # the input form: one record per new initiative, see USER_INPUT_SOURCE


@dataclass(frozen=True)
class SourceConfig:
    key: str  # short id, used in dag_id/task_id
    sheet_name: str  # sheet in the source workbook
    extract_table: str  # bronze table name, as in the data model
    business_unit: str  # stored in Owner.category, same labels as before
    columns: tuple[str, ...]
    mode: str = SHEET

    @property
    def asset_uri(self) -> str:
        return f"ai-cockpit://bronze/{self.extract_table}"


SOURCES: tuple[SourceConfig, ...] = (
    SourceConfig(
        key="it",
        sheet_name="IT",
        extract_table="IT_Initiatives_Extract",
        business_unit="IT",
        columns=(
            "Number", "Name", "Description", "Owner", "Department", "Flagship",
            "Strategic Link", "AI Layer", "Status", "Solution Type",
            "Solution Feasibility", "Impediments", "High-Level Cost Assessment",
            "Expected Outcome", "Added Value",
        ),
    ),
    SourceConfig(
        key="50hertz",
        sheet_name="50Hertz",
        extract_table="50Hertz_Initiatives_Extract",
        business_unit="50 Hertz",
        columns=(
            "Number", "Name", "Description", "Owner", "Department", "Flagship",
            "Strategic Link", "Solution Type", "AI Layer", "Status", "Value",
            "Solution Feasibility", "Impediments", "High-Level Cost Assessment",
            "Expected Outcome", "2026",
        ),
    ),
    SourceConfig(
        key="corporate_onesap",
        sheet_name="Corporate & OneSAP+",
        extract_table="CorporateOneSAP_Initiatives_Extract",
        business_unit="Corporate",
        columns=(
            "Number", "Name", "Description", "Owner", "Department", "Flagship",
            "Strategic Link", "Strategic Link ETB", "Solution Type", "AI Layer",
            "Status", "Solution Feasibility", "Impediments",
            "High-Level Cost Assessment", "Expected Outcome", "Added Value",
        ),
    ),
    SourceConfig(
        key="etb",
        sheet_name="ETB",
        extract_table="ETB_Initiatives_Extract",
        business_unit="ETB",
        columns=(
            "Number", "Kolom1", "Name", "Description", "Owner", "Department",
            "Flagship", "Strategic Link ETB", "Strategic Link", "Solution Type",
            "AI Layer", "Status", "Value", "Complexity", "Solution Feasibility",
            "Impediments", "High-Level Cost Assessment", "Expected Outcome",
            "Added Value", "Timing start", "Timing delivery",
        ),
    ),
)

# The input form's bronze table (models.USER_INPUT_TABLE). Not a sheet, so it is
# not in SOURCES (RawToBronze, seed_config and the extract tables are sheet-only);
# the BronzeToSilver meta DAG renders a DAG for it too, in its own mode:
# incremental (only records without a BusinessTransaction yet), no soft delete,
# the business unit per record (from its owner), typed drivers instead of the
# sheet heuristic (transforms.user_input_heuristic).
USER_INPUT_SOURCE = SourceConfig(
    key="user_input",
    sheet_name="",
    extract_table="UserInput_Initiatives_Extract",
    business_unit="",
    columns=(),
    mode=USER_INPUT,
)

BRONZE_TO_SILVER_SOURCES: tuple[SourceConfig, ...] = (*SOURCES, USER_INPUT_SOURCE)

SOURCES_BY_KEY = {source.key: source for source in BRONZE_TO_SILVER_SOURCES}

# Asset emitted once the config/reference tables have been (re)seeded.
CONFIG_ASSET_URI = "ai-cockpit://config/reference-tables"
