"""File sensor: waits for the source Excel file to appear in the source
folder and to have finished being written.

Guards against two real failure modes: (1) picking up a file mid-copy, by
requiring its size to be stable across a short interval, and (2)
reprocessing an unchanged file on every DAG run, by only reporting "found"
once the file's mtime is newer than the last run it successfully handed off
to the raw-to-silver operator (tracked via a small marker file in the same
folder — touched by RawToSilverOperator after a successful import).
"""
from __future__ import annotations

import time
from pathlib import Path

from airflow.sdk.bases.sensor import BaseSensorOperator

MARKER_NAME = ".ai_cockpit_import.last_processed"


class SourceFileSensor(BaseSensorOperator):
    """Pokes `source_dir` for a file matching `filename_glob`.

    On success, pushes the resolved path to XCom (key "source_file_path")
    and its modification time (key "source_file_mtime"), so the downstream
    raw-to-silver operator does not repeat the glob/selection logic.
    """

    template_fields = ("source_dir", "filename_glob")

    def __init__(self, *, source_dir: str, filename_glob: str = "*.xlsx", **kwargs):
        super().__init__(**kwargs)
        self.source_dir = source_dir
        self.filename_glob = filename_glob

    def poke(self, context) -> bool:
        source_dir = Path(self.source_dir)
        if not source_dir.is_dir():
            self.log.warning("Source directory %s does not exist yet", source_dir)
            return False

        candidates = [p for p in source_dir.glob(self.filename_glob) if p.is_file()]
        if not candidates:
            self.log.info("No file matching %s in %s yet", self.filename_glob, source_dir)
            return False

        # Multiple matches: take the most recently modified one.
        source_file = max(candidates, key=lambda p: p.stat().st_mtime)

        marker = source_dir / MARKER_NAME
        last_processed_mtime = marker.stat().st_mtime if marker.exists() else 0.0
        if source_file.stat().st_mtime <= last_processed_mtime:
            self.log.info("%s has not changed since the last successful import", source_file)
            return False

        # Settle check: the file size must be stable, i.e. not mid-copy.
        size_before = source_file.stat().st_size
        time.sleep(2)
        if not source_file.exists() or source_file.stat().st_size != size_before:
            self.log.info("%s is still being written, waiting", source_file)
            return False

        context["ti"].xcom_push(key="source_file_path", value=str(source_file))
        context["ti"].xcom_push(key="source_file_mtime", value=source_file.stat().st_mtime)
        self.log.info("Found new source file: %s", source_file)
        return True
