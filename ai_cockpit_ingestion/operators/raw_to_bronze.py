"""Raw-to-Bronze operator: copies one raw source sheet 1:1 into its extract
table (see sources.SOURCES).

No cleaning or type casting here — every cell is stored as text exactly as
in the sheet, only rows without a Name are skipped (the 50Hertz sheet, for
example, has ~1M formatted but empty rows). The extract is append-only:
each load is one BusinessTransaction; its rows are appended in one database
transaction, all stamped with that transaction's ID, and earlier loads are
never updated or deleted. BronzeToSilver reads the latest successful load
(lineage.latest_bronze_load).
"""
from __future__ import annotations

import polars as pl
from airflow.models.baseoperator import BaseOperator
from sqlalchemy import insert, update
from sqlalchemy.orm import Session

from ai_cockpit_ingestion.db import get_engine
from ai_cockpit_ingestion.lineage import STATUS_SUCCESS, mark_failed, start_transaction, utcnow
from ai_cockpit_ingestion.models import (
    EXTRACT_TABLES,
    KIND_RAW_TO_BRONZE,
    LOAD_COLUMNS,
    RECORD_ID_COLUMN,
    BusinessTransaction,
)
from ai_cockpit_ingestion.sources import SOURCES_BY_KEY

# Sheet row of the first data row (row 1 is the header).
FIRST_DATA_ROW = 2


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

        df = df.with_row_index("_idx").filter(
            pl.col("Name").is_not_null() & (pl.col("Name").str.strip_chars() != "")
        )
        load_timestamp = utcnow()
        engine = get_engine(self.db_path)
        transaction_id = start_transaction(
            engine,
            kind=KIND_RAW_TO_BRONZE,
            extract_table=source.extract_table,
            business_unit=source.business_unit,
            source_file=str(source_file_path),
            load_timestamp=load_timestamp,
        )
        rows = [
            {
                **{column: _cell_text(row[column]) for column in source.columns},
                "_BusinessTransactionId": transaction_id,
                "_LoadTimestamp": load_timestamp,
                "_SourceFile": str(source_file_path),
                "_SourceRow": row["_idx"] + FIRST_DATA_ROW,
            }
            for row in df.iter_rows(named=True)
        ]

        table = EXTRACT_TABLES[source.extract_table]
        try:
            with Session(engine) as session, session.begin():
                if rows:
                    session.execute(insert(table), rows)
                session.execute(
                    update(BusinessTransaction)
                    .where(BusinessTransaction.id == transaction_id)
                    .values(status=STATUS_SUCCESS, finished_at=utcnow(), rows_read=len(rows), inserted=len(rows))
                )
        except Exception as error:
            mark_failed(engine, transaction_id, error)
            raise
        finally:
            engine.dispose()

        self.log.info(
            "Appended %d rows to %s (business transaction %d)", len(rows), source.extract_table, transaction_id
        )
        return transaction_id
