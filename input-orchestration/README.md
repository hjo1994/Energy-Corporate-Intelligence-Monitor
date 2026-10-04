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
  requirements.txt            # apache-airflow>=3.0
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

## Lokal ausführen

```bash
./scripts/run_local.sh standalone          # einmalig: legt .venv + .airflow_home an, startet Airflow
./scripts/run_local.sh dags unpause ai_initiatives_import
./scripts/run_local.sh dags trigger ai_initiatives_import
```

Beobachtet standardmäßig `../data/` (wo die echte Quell-Excel liegt) und
schreibt die SQLite-Ausgabe nach `.airflow_home/ai_cockpit.db` — beides per
Env-Variable überschreibbar (`SOURCE_DIR`, `AI_COCKPIT_DB_PATH`). Sowohl
`.venv/` als auch `.airflow_home/` sind gitignored.

**Wichtig — Airflow 3, nicht 2.x:** Die zuerst installierte Version war
`apache-airflow` latest = **3.3.2**; mein ursprünglicher Code war gegen die
2.x-API geschrieben. Die alten Importpfade (`airflow.sensors.base`,
`airflow.models.BaseOperator`, `from airflow import DAG`) funktionieren in 3.x
nur noch über einen Deprecation-Shim. Umgestellt auf die kanonischen
Airflow-3-Importe: `airflow.sdk.bases.sensor.BaseSensorOperator`,
`airflow.sdk.BaseOperator`, `airflow.sdk.DAG`.

`ai_cockpit_ingestion/models.py` ist eine von Hand gepflegte Kopie des
Backend-Datenmodells (separate Deployments/Images, kein gemeinsames Paket in
diesem Prototyp-Stadium — siehe Kommentar im Modul).

## Verifiziert

**End-to-End über einen echten lokalen Airflow-3-Lauf** (Scheduler,
DAG-Processor, Triggerer, API-Server — via `scripts/run_local.sh standalone`):
DAG gegen die echte Quell-Excel ausgeführt, beide Tasks erfolgreich,
`.airflow_home/ai_cockpit.db` enthält die erwarteten 160 Initiativen/74
Owner. Dabei auch den Re-Run-Schutz bestätigt: ein zweiter, manuell
getriggerter Lauf direkt danach erkennt korrekt "Datei unverändert seit
letztem Import" und überspringt den Import (`SourceFileSensor`,
Marker-Datei), statt unnötig neu zu schreiben.

Nach der Umstellung auf `SolutionType`/`ValueType` als Referenz-/Lookup-
Tabellen (Marker-Datei gelöscht, DAG erneut erfolgreich durchgelaufen):
11 `SolutionType`- und 7 `ValueType`-Einträge aus dem `Variables`-Sheet
seedet, 69/160 Initiativen mit `SolutionType` verknüpft (43 % — der Rest ist
Freitext statt Katalog-Auswahl, siehe Root-README), 156/160 mit `ValueType`,
66/160 mit `value_score`, 67/160 mit `solution_complexity_score`.

Die Transform-Logik selbst wurde zusätzlich standalone gegen die echte
Quell-Excel laufen lassen: dabei zwei Datenqualitätsfälle gefunden, die der
Code jetzt explizit behandelt statt sie zu verschlucken:

- Ein Status-Wert war Freitext statt Dropdown-Auswahl
  (`"In development by Delaware. ETA 7.2026"`) — wird wie jeder nicht
  erkannte Status auf `"Unknown"` gemappt, mit Warn-Log des Originalwerts.
  Insgesamt 18 von 160 Zeilen (11 %) landen aktuell auf `"Unknown"`.
- Die `Value`-Spalte mischt T-Shirt-Größen (Text) und 1–10-Zahlen in
  derselben Spalte; ein Dataframe-Reader, der dafür einen einzigen Spaltentyp
  wählt (Polars: `String`), liefert die ETB-Zahlen dann als `"9"` statt `9`
  — `derive_value_score` behandelt das jetzt explizit.

Nicht erkannte `Status`-Werte sind kein Implementierungsfehler, sondern ein
Hinweis auf Dateneingabe-Probleme in der Quelle — siehe Root-README für die
vollständige Liste der Status-/Feasibility-Werte laut `Variables`-Sheet (9
Status- statt der im ersten Dashboard-Entwurf verwendeten 4, 5 statt 4
Feasibility-Größen XS–XL) und die noch zu bestätigenden Mapping-Annahmen.

Noch nicht gemacht: Unit-Tests für `transforms/normalize.py`; ein echter
Lauf gegen die SQLite-Datei auf einem RWX-Volume mit zwei getrennten
Pods (Input Orchestration + Backend) — bisher nur lokal auf einer Platte
verifiziert, das eigentliche Interim-Risiko (Netzwerk-Storage-Locking)
ist damit noch nicht getestet.
