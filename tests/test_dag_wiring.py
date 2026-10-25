"""Every new bronze load starts its bronze_to_silver DAG: the Dataset each
RawToBronze load task emits is exactly the schedule of the matching DAG, and
the input form's DAG also listens to its table's Dataset (plus a fallback
schedule every minute). Parses the real DAG files (pytest tests/)."""
from pathlib import Path

import pytest
from airflow.models import DagBag
from airflow.timetables.datasets import DatasetOrTimeSchedule

from ai_cockpit_ingestion.sources import SOURCES, USER_INPUT_SOURCE


@pytest.fixture(scope="module")
def dagbag():
    bag = DagBag(dag_folder=str(Path(__file__).parent.parent / "dags"), include_examples=False)
    assert bag.import_errors == {}
    return bag


def _scheduled_on(dag):
    return {uri for uri, _ in dag.timetable.dataset_condition.iter_datasets()}


def test_every_extract_load_emits_the_dataset_its_silver_dag_is_scheduled_on(dagbag):
    raw = dagbag.get_dag("raw_to_bronze")
    for source in SOURCES:
        outlets = {d.uri for d in raw.get_task(f"load_{source.key}").outlets}
        assert outlets == {source.asset_uri}
        assert _scheduled_on(dagbag.get_dag(f"bronze_to_silver_{source.key}")) == {source.asset_uri}


def test_user_input_dag_runs_on_its_dataset_and_every_minute(dagbag):
    dag = dagbag.get_dag("bronze_to_silver_user_input")
    assert isinstance(dag.timetable, DatasetOrTimeSchedule)
    assert _scheduled_on(dag) == {USER_INPUT_SOURCE.asset_uri}
    assert dag.timetable.timetable._expression == "* * * * *"
    assert (dag.max_active_runs, dag.catchup) == (1, False)
