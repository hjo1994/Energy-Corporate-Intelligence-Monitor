"""Environment-based configuration for the Input Orchestration DAG."""
import os
from pathlib import Path

SOURCE_DIR = Path(os.environ.get("SOURCE_DIR", "/opt/airflow/data/source"))
SOURCE_FILENAME_GLOB = os.environ.get("SOURCE_FILENAME_GLOB", "*.xlsx")

# The source workbook has one raw sheet per business unit (IT, 50Hertz,
# Corporate & OneSAP+, ETB) with inconsistent columns, plus one already
# consolidated "EliaGroup" sheet (verified: same ~160 rows as the sum of the
# four raw sheets, each tagged with its originating BU in the "Source"
# column). We read that single consolidated sheet rather than reconciling
# four different raw schemas ourselves.
SOURCE_SHEET = os.environ.get("SOURCE_SHEET", "EliaGroup")

DB_PATH = Path(os.environ.get("AI_COCKPIT_DB_PATH", "/opt/airflow/data/db/ai_cockpit.db"))

# The workbook's own planning year, used to resolve a bare quarter label
# ("Q1".."Q4") in "Timing start"/"Timing delivery" into a date — see
# transforms.normalize.derive_timing_date for why this is a flagged
# assumption, not a fact read from the data.
PLANNING_YEAR = int(os.environ.get("AI_COCKPIT_PLANNING_YEAR", "2026"))
