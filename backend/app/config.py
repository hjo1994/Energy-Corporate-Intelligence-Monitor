"""Environment-based configuration."""
import os
from pathlib import Path


def get_db_path() -> Path:
    # Mount point of the shared (interim) SQLite file — an infra decision,
    # hence overridable.
    return Path(os.environ.get("AI_COCKPIT_DB_PATH", "/data/db/ai_cockpit.db"))
