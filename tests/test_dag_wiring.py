"""The bronze_to_silver factory, parsed from the real DAG files: one DAG per
bronze table, each with its own sensor on its own table (pytest tests/)."""
from pathlib import Path

import pytest
from airflow.models import DagBag

from ai_cockpit_ingestion.sources import BRONZE_TO_SILVER_SOURCES, SOURCES


@pytest.fixture(scope="module")
def dagbag():
    bag = DagBag(dag_folder=str(Path(__file__).parent.parent / "dags"), include_examples=False)
    assert bag.import_errors == {}
    return bag


def test_one_dag_per_bronze_table(dagbag):
    assert {d for d in dagbag.dag_ids if d.startswith("bronze_to_silver")} == {
        f"bronze_to_silver_{s.key}" for s in BRONZE_TO_SILVER_SOURCES
    }


@pytest.mark.parametrize("source", BRONZE_TO_SILVER_SOURCES, ids=lambda s: s.key)
def test_each_dag_waits_with_its_own_sensor_on_its_own_table(dagbag, source):
    dag = dagbag.get_dag(f"bronze_to_silver_{source.key}")
    assert dag.timetable.summary == "@continuous"
    assert (dag.max_active_runs, dag.catchup) == (1, False)
    sensor = dag.get_task("wait_for_new_bronze")
    assert sensor.source_key == source.key
    assert (sensor.mode, sensor.poke_interval, sensor.soft_fail) == ("reschedule", 60, True)
    assert sensor.timeout == 24 * 3600
    assert dag.get_task("bronze_to_silver").upstream_task_ids == {"wait_for_new_bronze"}


def test_raw_to_bronze_still_emits_one_dataset_per_extract(dagbag):
    raw = dagbag.get_dag("raw_to_bronze")
    for source in SOURCES:
        assert {d.uri for d in raw.get_task(f"load_{source.key}").outlets} == {source.asset_uri}


def test_silver_to_gold_waits_for_silver_changes(dagbag):
    dag = dagbag.get_dag("silver_to_gold")
    assert dag.timetable.summary == "@continuous"
    assert (dag.max_active_runs, dag.catchup) == (1, False)
    sensor = dag.get_task("wait_for_silver_changes")
    assert (sensor.mode, sensor.poke_interval, sensor.soft_fail) == ("reschedule", 60, True)
    assert dag.get_task("silver_to_gold").upstream_task_ids == {"wait_for_silver_changes"}
