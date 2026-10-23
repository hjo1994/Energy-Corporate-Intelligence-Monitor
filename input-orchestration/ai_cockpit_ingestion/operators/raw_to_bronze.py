"""Raw-to-Bronze operator: copies one raw source sheet 1:1 into its extract
table (see sources.SOURCES).

No cleaning or type casting here — every cell is stored as text exactly as
in the sheet, only rows without a Name are skipped (the 50Hertz sheet, for
example, has ~1M formatted but empty rows). Each load replaces the whole
extract in one transaction, so readers never see a half-written table.
"""
from __future__ import annotations

import datetime

import polars as pl
from airflow.sdk import BaseOperator
from sqlalchemy import delete, insert

from ai_cockpit_ingestion.db import get_engine
from ai_cockpit_ingestion.models import EXTRACT_TABLES
from ai_cockpit_ingestion.sources import SOURCES_BY_KEY

# Sheet row of the first data row (row 1 is the header).
FIRST_DATA_ROW = 2


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
        missing = [c for c in source.columns if c not in df.columns]
        unexpected = [c for c in df.columns if c not in source.columns and not c.startswith("__UNNAMED")]
        if missing:
            # A renamed/removed column would silently empty a silver field.
            raise ValueError(f"Sheet {source.sheet_name!r} is missing columns {missing}")
        if unexpected:
            self.log.warning(
                "Sheet %r has columns not in the data model, not loaded: %s", source.sheet_name, unexpected
            )

        df = df.with_row_index("_idx").filter(
            pl.col("Name").is_not_null() & (pl.col("Name").str.strip_chars() != "")
        )
        load_timestamp = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        rows = [
            {
                **{column: _cell_text(row[column]) for column in source.columns},
                "_LoadTimestamp": load_timestamp,
                "_SourceFile": str(source_file_path),
                "_SourceRow": row["_idx"] + FIRST_DATA_ROW,
            }
            for row in df.iter_rows(named=True)
        ]

        table = EXTRACT_TABLES[source.extract_table]
        engine = get_engine(self.db_path)
        with engine.begin() as connection:
            connection.execute(delete(table))
            if rows:
                connection.execute(insert(table), rows)
        engine.dispose()

        self.log.info("Loaded %d rows into %s", len(rows), source.extract_table)
        return len(rows)
