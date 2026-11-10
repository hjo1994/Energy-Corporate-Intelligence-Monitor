"""Environment-based configuration."""
import os
from pathlib import Path


def get_db_path() -> Path:
    # Mount point of the shared (interim) SQLite file — an infra decision,
    # hence overridable.
    return Path(os.environ.get("AI_COCKPIT_DB_PATH", "/data/db/ai_cockpit.db"))


def initiative_input_enabled() -> bool:
    """Feature switch for the input form (POST /api/initiatives, "+ New initiative" in the UI).
    Off where the database cannot be written by the Backend (e.g. a read-only volume)."""
    return os.environ.get("AI_COCKPIT_ENABLE_INITIATIVE_INPUT", "true").strip().lower() not in ("false", "0", "no", "off")


def airflow_api() -> tuple[str, str, str] | None:
    """Airflow REST API of the input orchestration (URL, user, password), for the Dataset
    event after a user action (app/pipeline.py); None when AI_COCKPIT_AIRFLOW_URL is unset."""
    url = os.environ.get("AI_COCKPIT_AIRFLOW_URL", "").strip()
    if not url:
        return None
    return url, os.environ.get("AI_COCKPIT_AIRFLOW_USER", ""), os.environ.get("AI_COCKPIT_AIRFLOW_PASSWORD", "")


# TEMPORARY (demo): every signed-in user gets the approver rights (inbox, decisions), whatever
# their role in AppUser; their stored role and the Users page stay untouched. To revert: set
# AI_COCKPIT_DEMO_ALL_APPROVERS=false, or delete this function and its one use in app/auth.py.
def demo_all_approvers() -> bool:
    return os.environ.get("AI_COCKPIT_DEMO_ALL_APPROVERS", "true").strip().lower() not in ("false", "0", "no", "off")
