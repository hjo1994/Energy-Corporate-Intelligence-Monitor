#!/usr/bin/env bash
# Local dev runner for the Input Orchestration DAG — no Kubernetes, no
# Docker, just this folder's venv. Sets up an isolated AIRFLOW_HOME under
# this folder and execs whatever `airflow` subcommand is passed through,
# e.g.:
#   ./scripts/run_local.sh standalone
#   ./scripts/run_local.sh dags trigger ai_initiatives_import
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q apache-airflow
  .venv/bin/pip install -q -e .
fi
# shellcheck disable=SC1091
source .venv/bin/activate

export AIRFLOW_HOME="$(pwd)/.airflow_home"
export AIRFLOW__CORE__DAGS_FOLDER="$(pwd)/dags"
export AIRFLOW__CORE__LOAD_EXAMPLES=false
# Watched source folder and SQLite output, both local to this repo so there
# is nothing to configure before a first run.
export SOURCE_DIR="${SOURCE_DIR:-$(cd .. && pwd)/data}"
export AI_COCKPIT_DB_PATH="${AI_COCKPIT_DB_PATH:-$AIRFLOW_HOME/ai_cockpit.db}"

exec airflow "$@"
