"""The DAG chain, parsed from the real DAG files (pytest tests/): event-driven,
no DAG runs continuously or polls.

raw_to_bronze -> Dataset of each extract -> bronze_to_silver_<key>
Backend (REST API) -> Dataset of UserActionExtracts -> bronze_to_silver_user_input
bronze_to_silver_* -> silver Dataset (only when silver was written) -> silver_to_gold
"""
from pathlib import Path

import pytest
from airflow.models import DagBag

from ai_cockpit_ingestion.sources import BRONZE_TO_SILVER_SOURCES, SILVER_ASSET_URI, SOURCES


@pytest.fixture(scope="module")
def dagbag():
    bag = DagBag(dag_folder=str(Path(__file__).parent.parent / "dags"), include_examples=False)
    assert bag.import_errors == {}
    return bag


def _scheduled_on(dag) -> set[str]:
    condition = dag.timetable.dataset_condition
    return {uri for uri, _ in condition.iter_datasets()}


def test_one_dag_per_bronze_table(dagbag):
    assert {d for d in dagbag.dag_ids if d.startswith("bronze_to_silver")} == {
        f"bronze_to_silver_{s.key}" for s in BRONZE_TO_SILVER_SOURCES
    }


def test_no_dag_runs_continuously(dagbag):
    assert [d.dag_id for d in dagbag.dags.values() if d.timetable.summary == "@continuous"] == []


@pytest.mark.parametrize("source", BRONZE_TO_SILVER_SOURCES, ids=lambda s: s.key)
def test_each_dag_is_triggered_by_the_dataset_of_its_own_table(dagbag, source):
    dag = dagbag.get_dag(f"bronze_to_silver_{source.key}")
    assert _scheduled_on(dag) == {source.asset_uri}
    assert (dag.max_active_runs, dag.catchup) == (1, False)
    assert dag.get_task("silver_changed").upstream_task_ids == {"bronze_to_silver"}
    assert dag.get_task("silver_updated").upstream_task_ids == {"silver_changed"}
    assert {d.uri for d in dag.get_task("silver_updated").outlets} == {SILVER_ASSET_URI}
    assert dag.get_task("bronze_to_silver").outlets == []
    assert all(t.retries == 2 for t in dag.tasks)


def test_raw_to_bronze_emits_one_dataset_per_extract(dagbag):
    raw = dagbag.get_dag("raw_to_bronze")
    for source in SOURCES:
        assert {d.uri for d in raw.get_task(f"load_{source.key}").outlets} == {source.asset_uri}


def test_silver_to_gold_is_triggered_by_silver_and_once_a_day(dagbag):
    dag = dagbag.get_dag("silver_to_gold")
    assert _scheduled_on(dag) == {SILVER_ASSET_URI}
    assert "0 3 * * *" in dag.timetable.summary
    assert (dag.max_active_runs, dag.catchup) == (1, False)
    assert dag.get_task("silver_to_gold").retries == 2


@pytest.mark.parametrize(("counts", "force", "expected"), [
    ({"read": 1, "inserted": 1, "updated": 0}, False, True),
    ({"read": 3, "inserted": 0, "updated": 0, "unchanged": 3, "deactivated": 0}, False, False),
    ({"read": 0, "inserted": 0, "updated": 0}, True, True),
    (None, False, False),
])
def test_silver_to_gold_is_only_triggered_when_silver_was_written(counts, force, expected):
    import importlib.util

    spec = importlib.util.spec_from_file_location("b2s", Path(__file__).parent.parent / "dags" / "bronze_to_silver_dag.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class _TI:
        def xcom_pull(self, task_ids):
            assert task_ids == "bronze_to_silver"
            return counts

    assert module.wrote_silver(_TI(), {"force": force}) is expected
