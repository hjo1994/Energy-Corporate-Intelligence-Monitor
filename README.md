# Input Orchestration — Airflow DAG

Eigenes Kubernetes-Deployment. Ein DAG (`dags/ai_initiatives_import_dag.py`)
mit zwei Operatoren:

1. **`SourceFileSensor`** (`ai_cockpit_ingestion/operators/source_file_sensor.py`)
   — wartet im Quellordner auf eine `.xlsx`-Datei, prüft dass sie fertig
   geschrieben ist (Größe stabil über ein kurzes Intervall) und dass sie sich
   seit dem letzten erfolgreichen Import geändert hat (Marker-Datei
   `.ai_cockpit_import.last_processed` im Quellordner).
2. **`RawToSilverOperator`** (`ai_cockpit_ingestion/operators/raw_to_silver.py`)
   — liest das Sheet `EliaGroup` (Initiativen) und `Variables` (Typ-Kataloge)
   mit Polars, normalisiert die Felder (`ai_cockpit_ingestion/transforms/normalize.py`)
   und schreibt sie über SQLAlchemy in eine neue SQLite-Datei, die dann per
   atomarem `rename()` die aktive Datei ersetzt (siehe Interim-Entscheidung
   im Root-README).

Die Quell-Excel hat vier Rohdaten-Sheets (IT, 50Hertz, Corporate & OneSAP+,
ETB) mit uneinheitlichen Spalten, plus ein bereits konsolidiertes Sheet
`EliaGroup`, das denselben Datenbestand mit einheitlichem Spaltenschema und
einer `Source`-Spalte pro Zeile enthält (geprüft: Zeilenzahl ≈ Summe der vier
Rohblätter). Raw-to-Silver liest nur dieses eine Sheet, statt vier
unterschiedliche Rohschemata selbst zusammenzuführen.

## Struktur

```
input-orchestration/
  pyproject.toml              # macht ai_cockpit_ingestion im Airflow-Image importierbar
  requirements.txt            # apache-airflow==2.10.2
  scripts/
    run_local.sh              # lokaler Airflow-Lauf ohne Docker/K8s, siehe unten
  dags/
    ai_initiatives_import_dag.py
  ai_cockpit_ingestion/
    config.py                 # SOURCE_DIR, DB_PATH, PLANNING_YEAR etc. aus Env-Variablen
    models.py                 # SQLAlchemy-Modelle (Initiative, Owner, SolutionType, ValueType)
    transforms/
      normalize.py            # Status-/Aufwand-/Mehrwert-/Timing-Normalisierung
    operators/
      source_file_sensor.py
      raw_to_silver.py
```

