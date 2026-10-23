"""Environment-based configuration for the Input Orchestration DAGs."""
import os
from pathlib import Path

SOURCE_DIR = Path(os.environ.get("SOURCE_DIR", "/opt/airflow/data/source"))
# Narrow on purpose: the source folder also holds other workbooks (e.g. the
# "Value sizing" sheet), and the sensor picks the newest match.
SOURCE_FILENAME_GLOB = os.environ.get("SOURCE_FILENAME_GLOB", "2026 AI Initiatives*.xlsx")

# The source workbook has one raw sheet per business unit (IT, 50Hertz,
# Corporate & OneSAP+, ETB) — see sources.SOURCES. RawToBronze loads each
# into its own extract table. The workbook's consolidated "EliaGroup" sheet
# is no longer read: it lags behind the raw sheets (160 vs. 165 initiatives
# at the time of writing).
VARIABLES_SHEET = os.environ.get("VARIABLES_SHEET", "Variables")

DB_PATH = Path(os.environ.get("AI_COCKPIT_DB_PATH", "/opt/airflow/data/db/ai_cockpit.db"))

# The workbook's own planning year, used to resolve a bare quarter label
# ("Q1".."Q4") in "Timing start"/"Timing delivery" into a date — see
# transforms.normalize.derive_timing_date for why this is a flagged
# assumption, not a fact read from the data.
PLANNING_YEAR = int(os.environ.get("AI_COCKPIT_PLANNING_YEAR", "2026"))
