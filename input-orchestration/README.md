# Input Orchestration — Airflow DAGs (Bronze → Silber)

Eigenes Kubernetes-Deployment. Medallion-Aufbau laut
`solution documentation/Architecture.drawio` und `Logical Data Model.drawio`:

| DAG | Datei | Auslöser | Schreibt |
| --- | --- | --- | --- |
| `raw_to_bronze` | `dags/raw_to_bronze_dag.py` | stündlich, Sensor auf die Quell-Excel | 4 Extract-Tabellen (Bronze) |
| `seed_config` | `dags/seed_config_dag.py` | nur manuell, einmalig | Owner, SolutionType, ValueType, RiskClassification (Config) |
| `bronze_to_silver_<quelle>` (4×) | `dags/bronze_to_silver_dag.py` (Meta-DAG) | Asset der jeweiligen Extract-Tabelle | Initiative (Silber) |

1. **RawToBronze** — `SourceFileSensor` wartet auf eine neue/geänderte
   `2026 AI Initiatives*.xlsx` (Größe stabil, mtime neuer als die Marker-Datei
   `.ai_cockpit_import.last_processed`). Danach lädt je Quellblatt ein
   `RawToBronzeOperator` die Zeilen 1:1 als Text in seine Extract-Tabelle
   (`IT_Initiatives_Extract`, `50Hertz_Initiatives_Extract`,
   `CorporateOneSAP_Initiatives_Extract`, `ETB_Initiatives_Extract`) plus
   `_LoadTimestamp`, `_SourceFile`, `_SourceRow`. Leere Zeilen (ohne Name)
   werden übersprungen; fehlt eine Spalte des Datenmodells im Blatt, bricht
   der Task ab. Jeder Load-Task emittiert das Asset seiner Tabelle.
2. **SeedConfig** — Config-Tabellen sind einmalig zu befüllende
   Konfiguration. Der DAG legt nur fehlende Einträge an (nie Update/Delete):
   SolutionType/ValueType aus dem Blatt `Variables`, RiskClassification mit
   den 5 Stufen der Rahmenbetriebsvereinbarung KI, Owner aus den
   Owner/Department-Paaren der Extract-Tabellen (Category = Business Unit).
   Einmal nach dem ersten `raw_to_bronze`-Lauf starten.
3. **BronzeToSilver (Meta-DAG)** — `build_bronze_to_silver_dag()` erzeugt aus
   einem Template je Eintrag in `ai_cockpit_ingestion/sources.py` einen DAG
   `bronze_to_silver_<key>`, der auf das Asset seiner Extract-Tabelle
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
input-orchestration/
  dags/
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

## Lokal ausführen

```bash
./scripts/run_local.sh standalone              # einmalig: .venv + .airflow_home, startet Airflow
./scripts/run_local.sh dags unpause raw_to_bronze
./scripts/run_local.sh dags trigger raw_to_bronze
./scripts/run_local.sh dags trigger seed_config      # einmalig, nach dem ersten Bronze-Lauf
for d in it 50hertz corporate_onesap etb; do ./scripts/run_local.sh dags unpause bronze_to_silver_$d; done
```

Beim allerersten Lauf starten die Silber-DAGs schon nach `raw_to_bronze` und
schlagen fehl, solange die Config leer ist. Deshalb die Silber-DAGs erst nach
`seed_config` aktivieren (oder danach einmal manuell triggern). Um eine
unveränderte Excel erneut zu laden, die Marker-Datei in `data/` löschen.

**Airflow 3, nicht 2.x:** kanonische Importe aus `airflow.sdk` (`DAG`,
`BaseOperator`, `Asset`, `task`, `bases.sensor.BaseSensorOperator`).

## Verifiziert (23.10.2026)

Echter lokaler Lauf mit Airflow 3.3.2 (`airflow standalone`) gegen die echte
Quell-Excel:

- `raw_to_bronze`: 17 IT, 53 50Hertz, 29 Corporate & OneSAP+, 66 ETB = 165
  Zeilen. Das frühere EliaGroup-Blatt hatte nur 160 (u. a. fehlen dort „Ask
  Nova“, „Smart Image Database (SID)“).
- `seed_config`: 11 SolutionType, 7 ValueType, 5 RiskClassification, 80 Owner.
- Alle vier `bronze_to_silver_*` liefen automatisch über die Assets an,
  parallel, erfolgreich: 165 Initiativen. Risikostufen 59 × 1, 87 × 2,
  13 × 3, 6 × 4. Summe ≈ 39,8 Mio. € hypothetisch, ≈ 9,8 Mio. € Potenzial,
  ≈ 15,6 Mio. € Kosten/Jahr.
- Erneuter Lauf eines Silber-DAGs ersetzt nur die eigenen Zeilen (weiter 165).
- `pytest tests/`: 7 Tests grün.

Bekannte Datenlücken (Quelle, kein Code-Fehler): 23 Initiativen ohne Owner
in der Excel (22 ETB, 1 Corporate) → `owner_id` NULL; 102 mit Freitext statt
Katalog-SolutionType → `solution_type_id` NULL; 19 mit nicht erkanntem
Status → Stage `Unknown`.
