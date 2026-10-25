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
