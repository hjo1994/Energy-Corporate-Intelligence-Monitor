# Input Orchestration — Airflow DAGs (Bronze → Silber)

Eigenes Kubernetes-Deployment. Medallion-Aufbau laut
`solution documentation/Architecture.drawio` und `Logical Data Model.drawio`:

| DAG | Datei | Auslöser | Schreibt |
| --- | --- | --- | --- |
| `raw_to_bronze` | `dags/raw_to_bronze_dag.py` | stündlich, Sensor auf die Quell-Excel | 4 Extract-Tabellen (Bronze) |
| `seed_config` | `dags/seed_config_dag.py` | nur manuell, einmalig | Owner, SolutionType, ValueType, RiskClassification (Config) |
| `bronze_to_silver_<quelle>` (4×) | `dags/bronze_to_silver_dag.py` (Meta-DAG) | Dataset der jeweiligen Extract-Tabelle | Initiative (Silber) |

1. **RawToBronze** — `SourceFileSensor` wartet auf eine neue/geänderte
   `2026?AI?Initiatives*.xlsx` (passt auf `2026_AI_Initiatives_Elia_Group.xlsx` in
   `data/sources/` und auf die Schreibweise mit Leerzeichen; Größe stabil, mtime neuer als die Marker-Datei
   `.ai_cockpit_import.last_processed`). Danach lädt je Quellblatt ein
   `RawToBronzeOperator` die Zeilen 1:1 als Text in seine Extract-Tabelle
   (`IT_Initiatives_Extract`, `50Hertz_Initiatives_Extract`,
   `CorporateOneSAP_Initiatives_Extract`, `ETB_Initiatives_Extract`) plus
   `_LoadTimestamp`, `_SourceFile`, `_SourceRow`. Leere Zeilen (ohne Name)
   werden übersprungen; fehlt eine Spalte des Datenmodells im Blatt, bricht
   der Task ab. Jeder Load-Task emittiert das Dataset seiner Tabelle.
2. **SeedConfig** — Config-Tabellen sind einmalig zu befüllende
   Konfiguration. Der DAG legt nur fehlende Einträge an (nie Update/Delete):
   SolutionType/ValueType aus dem Blatt `Variables`, RiskClassification mit
   den 5 Stufen der Rahmenbetriebsvereinbarung KI, Owner aus den
   Owner/Department-Paaren der Extract-Tabellen (Category = Business Unit).
   Nach dem ersten `raw_to_bronze`-Lauf manuell starten, später erneut, wenn
   neue Owner oder Katalogeinträge dazukommen (Silber legt keine an).
3. **BronzeToSilver (Meta-DAG)** — `build_bronze_to_silver_dag()` erzeugt aus
   einem Template je Eintrag in `ai_cockpit_ingestion/sources.py` einen DAG
   `bronze_to_silver_<key>`, der auf das Dataset seiner Extract-Tabelle
   scheduled ist. Der `BronzeToSilverOperator` normalisiert Status → Stage
   und Timing, verknüpft **nur bestehende** Config-Einträge (Unbekanntes
   bleibt NULL und wird geloggt), schätzt die Value-Attribute
   (`transforms/value_heuristic.py`) und die Risikostufe
   (`transforms/risk_heuristic.py`) und ersetzt in einer Transaktion die
   Initiativen seiner Business Unit. Eine neue Quelle braucht nur einen
   neuen `SourceConfig`-Eintrag.

Die Marker-Datei wird erst gesetzt, wenn alle vier Extrakte geladen sind.

## Heuristiken (Schätzungen, keine Messwerte)

- **Value** (`value_heuristic.py`, „Heuristik v2: Buckets einzeln“ aus dem
  Thread *Nutzen-Quantifizierung*, 1:1 portiert aus `data/value_heuristic.py`):
  Jeder der vier Buckets wird mit seiner eigenen Value-Sizing-Formel
  gerechnet. Treiber: Value-Score → Reichweite, SolutionType-Familie →
  Wirkung je Fall, Flagship → Kosten je Fehler/Ereignis/Verzug. Hypothetischer
  Nutzen = Summe der Buckets; Potenzial = Summe × ConfidenceScore ×
  DeliveryScore. Gegen `data/value_estimates_heuristic.csv` geprüft:
  identisch für alle 160 Initiativen des alten EliaGroup-Blatts.
- **Risiko** (`risk_heuristic.py`): Regelkette aus Name/Beschreibung/
  Expected Outcome/Added Value und SolutionType. Automatisierte
  Entscheidungen/Profilbildung über Beschäftigte → 4; Beschäftigtendaten,
  Leistungs-/Verhaltensauswertung → 3; Assistenten/Ticket-Routing → 2;
  technische Modelle ohne Personenbezug → 1; sonst 2. Stufe 5 wird nie
  geschätzt. Übereinstimmung mit `risiko/risk_classification_estimates.csv`:
  147 von 160 (alle Stufe-4-Fälle, 13 von 14 Stufe-3-Fällen).

## Datenbank

Interim weiter eine SQLite-Datei (`AI_COCKPIT_DB_PATH`). Weil jetzt mehrere
DAGs in dieselbe Datei schreiben, entfällt der frühere atomare
Datei-Tausch: Jeder Task schreibt in genau einer kurzen Transaktion
(Backend sieht bis zum Commit den alten Stand), parallele Schreiber warten
über das SQLite-Busy-Timeout (120 s). Tabellen legt `db.get_engine()`
idempotent an.

## Struktur

```
(Repo-Root dieses Branches)
  pyproject.toml / poetry.lock   # Poetry, Quellen: Firmen-Spiegel
  requirements.txt               # apache-airflow==2.10.2 + Laufzeit-Pakete
  data/sources/                  # Quell-Excel dieses Deployments
  dags/
    dependency_loader.py         # installiert polars/fastexcel im Cluster nach, falls sie fehlen
    raw_to_bronze_dag.py
    seed_config_dag.py
    bronze_to_silver_dag.py      # Meta-DAG: ein DAG je Extract-Tabelle
  ai_cockpit_ingestion/
    config.py                    # SOURCE_DIR, SOURCE_FILENAME_GLOB, DB_PATH, PLANNING_YEAR
    sources.py                   # die 4 Quellblätter: Tabelle, Business Unit, Spalten
    models.py                    # Bronze-, Config- und Silber-Tabellen (SQLAlchemy)
    db.py
    operators/
      source_file_sensor.py
      raw_to_bronze.py
      seed_config.py
      bronze_to_silver.py
    transforms/
      normalize.py               # Status-/Timing-/Komplexitäts-Normalisierung, Katalog-Matching
      value_heuristic.py
      risk_heuristic.py
  tests/test_transforms.py
```

## Airflow 2.10 (dieser Branch)

Dieser Branch läuft auf **Airflow 2.10.2 mit Python 3.11** (Plattform-Image),
`main` dagegen auf Airflow 3. Der Code ist derselbe bis auf die Importe:

| Airflow 3 (`main`) | Airflow 2.10 (hier) |
| --- | --- |
| `from airflow.sdk import DAG` | `from airflow import DAG` |
| `from airflow.sdk import BaseOperator` | `from airflow.models.baseoperator import BaseOperator` |
| `from airflow.sdk.bases.sensor import BaseSensorOperator` | `from airflow.sensors.base import BaseSensorOperator` |
| `from airflow.sdk import task` | `from airflow.decorators import task` |
| `Asset(name=..., uri=...)` | `Dataset(uri)` |

Jede DAG-Datei importiert zuerst `dependency_loader` (wie bisher). Airflow
2.10 bringt **SQLAlchemy 1.4** mit; der Code ist darauf getestet (der
DELETE im Silber-Operator läuft deshalb ohne Autoflush, siehe Kommentar dort).
Pfade im Cluster: `SOURCE_DIR=/data/source`, `AI_COCKPIT_DB_PATH=/data/db/ai_cockpit.db`.

## Lokal ausführen

Eigene venv mit Python 3.11 und den Airflow-Constraints (der Firmen-Spiegel
ist dafür nicht nötig, alle Pakete gibt es auf PyPI):

```bash
python3.11 -m venv .venv
.venv/bin/pip install "apache-airflow==2.10.2" polars fastexcel pytest \
  --constraint https://raw.githubusercontent.com/apache/airflow/constraints-2.10.2/constraints-3.11.txt
export AIRFLOW_HOME=$PWD/.airflow_home AIRFLOW__CORE__DAGS_FOLDER=$PWD/dags \
  AIRFLOW__CORE__LOAD_EXAMPLES=false PYTHONPATH=$PWD PATH=$PWD/.venv/bin:$PATH \
  SOURCE_DIR=<Ordner mit der Excel> AI_COCKPIT_DB_PATH=$PWD/.airflow_home/ai_cockpit.db
airflow db migrate
airflow dags test raw_to_bronze
airflow dags test seed_config
for d in it 50hertz corporate_onesap etb; do airflow dags test bronze_to_silver_$d; done
python -m pytest tests
```

Für das Dataset-Scheduling `airflow scheduler` starten und die DAGs
aktivieren (`airflow dags unpause ...`). Läuft parallel ein anderer
Airflow, `AIRFLOW__LOGGING__WORKER_LOG_SERVER_PORT` umstellen (Standard 8793).

Beim allerersten Lauf starten die Silber-DAGs schon nach `raw_to_bronze` und
schlagen fehl, solange die Config leer ist. Deshalb die Silber-DAGs erst nach
`seed_config` aktivieren (oder danach einmal manuell triggern). Um eine
unveränderte Excel erneut zu laden, die Marker-Datei
`.ai_cockpit_import.last_processed` im Quellordner löschen.

## Verifiziert (23.10.2026, Airflow 2.10.2, Python 3.11, SQLAlchemy 1.4.54)

Lokal gegen `data/sources/2026_AI_Initiatives_Elia_Group.xlsx`:

- Alle 6 DAGs laden ohne Import-Fehler.
- `raw_to_bronze`: 17 IT, 53 50Hertz, 29 Corporate & OneSAP+, 66 ETB = 165 Zeilen.
- `seed_config`: 11 SolutionType, 7 ValueType, 5 RiskClassification, 80 Owner.
- `bronze_to_silver_*`: 165 Initiativen, Risikostufen 59 × 1, 87 × 2, 13 × 3,
  6 × 4, ≈ 9,8 Mio. € Potenzial — identisch mit dem Lauf auf `main`
  (Airflow 3). Erneuter Lauf ersetzt nur die eigenen Zeilen.
- Mit laufendem Scheduler starteten alle vier Silber-DAGs automatisch
  (`dataset_triggered`) nach einem `raw_to_bronze`-Lauf.
- `pytest tests/`: 7 Tests grün.

**Nicht lokal geprüft:** Installation über den Firmen-Spiegel und
`poetry.lock`, der `dependency_loader` im Cluster, das echte Plattform-Image.

Bekannte Datenlücken (Quelle, kein Code-Fehler): 23 Initiativen ohne Owner
in der Excel (22 ETB, 1 Corporate) → `owner_id` NULL; 102 mit Freitext statt
Katalog-SolutionType → `solution_type_id` NULL; 19 mit nicht erkanntem
Status → Stage `Unknown`.
