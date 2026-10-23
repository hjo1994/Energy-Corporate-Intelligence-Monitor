"""BronzeToSilver meta DAG: generates one DAG per extract (bronze) table from
a single template.

For every entry in sources.SOURCES, `build_bronze_to_silver_dag` renders a
DAG `bronze_to_silver_<key>` that is scheduled on the Asset its RawToBronze
load task emits — so a fresh extract is turned into silver automatically,
and each source can also be re-run on its own. A new source sheet only needs
a new SourceConfig entry, no new DAG code.
"""
from __future__ import annotations

import datetime

from airflow.sdk import DAG, Asset

from ai_cockpit_ingestion import config
from ai_cockpit_ingestion.operators.bronze_to_silver import BronzeToSilverOperator
from ai_cockpit_ingestion.sources import SOURCES, SourceConfig


def build_bronze_to_silver_dag(source: SourceConfig) -> DAG:
    with DAG(
        dag_id=f"bronze_to_silver_{source.key}",
        description=f"{source.extract_table} -> Initiative (business unit {source.business_unit})",
        schedule=[Asset(name=source.extract_table, uri=source.asset_uri)],
        start_date=datetime.datetime(2026, 1, 1),
        catchup=False,
        max_active_runs=1,
        tags=["ai-cockpit", "input-orchestration", "silver"],
    ) as dag:
        BronzeToSilverOperator(
            task_id="bronze_to_silver",
            source_key=source.key,
            db_path=str(config.DB_PATH),
        )
    return dag


for _source in SOURCES:
    # Module-level names are how Airflow discovers DAGs in a file.
    globals()[f"bronze_to_silver_{_source.key}"] = build_bronze_to_silver_dag(_source)
