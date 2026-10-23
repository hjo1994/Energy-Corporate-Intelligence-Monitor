"""Raw-to-Bronze operator: copies one raw source sheet 1:1 into its extract
table (see sources.SOURCES).

No cleaning or type casting here — every cell is stored as text exactly as
in the sheet, only rows without a Name are skipped (the 50Hertz sheet, for
example, has ~1M formatted but empty rows). The extract is append-only:
each load appends its rows in one database transaction, all with the same
Timestamp and the source file in SourceFileID; earlier loads are never
updated or deleted. Readers take the latest load (lineage.latest_load_filter).
"""
from __future__ import annotations

import polars as pl
from airflow.models.baseoperator import BaseOperator
from sqlalchemy import insert

from ai_cockpit_ingestion.db import get_engine
from ai_cockpit_ingestion.lineage import utcnow
from ai_cockpit_ingestion.models import EXTRACT_TABLES, LOAD_COLUMNS, RECORD_ID_COLUMN
from ai_cockpit_ingestion.sources import SOURCES_BY_KEY

TECHNICAL_COLUMNS = (RECORD_ID_COLUMN, *LOAD_COLUMNS)


def check_no_technical_columns(sheet_name: str, sheet_columns) -> None:
    """A sheet column named like one of the loader's own columns would be
    silently confused with it, so such a sheet is rejected."""
    clashes = [c for c in sheet_columns if c.strip() in TECHNICAL_COLUMNS]
    if clashes:
        raise ValueError(
            f"Sheet {sheet_name!r} has columns {clashes} that clash with the extract table's "
            f"technical columns {list(TECHNICAL_COLUMNS)} — rename them in the workbook"
        )


def _cell_text(value) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text.strip() else None


class RawToBronzeOperator(BaseOperator):
    template_fields = ("db_path",)

    def __init__(self, *, source_key: str, db_path: str, sensor_task_id: str, **kwargs):
        super().__init__(**kwargs)
        self.source_key = source_key
        self.db_path = db_path
        self.sensor_task_id = sensor_task_id

    def execute(self, context) -> int:
        source = SOURCES_BY_KEY[self.source_key]
        source_file_path = context["ti"].xcom_pull(task_ids=self.sensor_task_id, key="source_file_path")
        if not source_file_path:
            raise RuntimeError(
                f"No source_file_path in XCom from task {self.sensor_task_id!r} — "
                "the SourceFileSensor must run first"
            )

        self.log.info("Reading %s (sheet %r)", source_file_path, source.sheet_name)
        # infer_schema_length=0: read every column as text, never let the
        # reader guess (and coerce) a type.
        df = pl.read_excel(
            source_file_path, sheet_name=source.sheet_name, engine="calamine", infer_schema_length=0
        )
        check_no_technical_columns(source.sheet_name, df.columns)
        missing = [c for c in source.columns if c not in df.columns]
        unexpected = [c for c in df.columns if c not in source.columns and not c.startswith("__UNNAMED")]
        if missing:
            # A renamed/removed column would silently empty a silver field.
            raise ValueError(f"Sheet {source.sheet_name!r} is missing columns {missing}")
        if unexpected:
            self.log.warning(
                "Sheet %r has columns not in the data model, not loaded: %s", source.sheet_name, unexpected
            )

        df = df.filter(
            pl.col("Name").is_not_null() & (pl.col("Name").str.strip_chars() != "")
        )
        load_timestamp = utcnow()
        # Inserted in sheet order, so ID follows the sheet's row order within a load.
        rows = [
            {
                **{column: _cell_text(row[column]) for column in source.columns},
                "Timestamp": load_timestamp,
                "SourceFileID": str(source_file_path),
            }
            for row in df.iter_rows(named=True)
        ]

        table = EXTRACT_TABLES[source.extract_table]
        engine = get_engine(self.db_path)
        with engine.begin() as connection:
            if rows:
                connection.execute(insert(table), rows)
        engine.dispose()

        self.log.info("Appended %d rows to %s (load %s)", len(rows), source.extract_table, load_timestamp)
        return len(rows)
