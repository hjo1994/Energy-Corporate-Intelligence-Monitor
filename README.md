# Input Orchestration — Airflow DAGs (Bronze → Silber → Gold)

Eigenes Kubernetes-Deployment. Medallion-Aufbau laut
`solution documentation/Architecture.drawio` und `Logical Data Model.drawio`:

| DAG | Datei | Auslöser | Schreibt |
| --- | --- | --- | --- |
| `raw_to_bronze` | `dags/raw_to_bronze_dag.py` | stündlich, Sensor auf die Quell-Excel | 4 Extract-Tabellen (Bronze) |
| `seed_config` | `dags/seed_config_dag.py` | nur manuell, einmalig | Owner, SolutionType, ValueType, RiskClassification (Config) |
| `bronze_to_silver_<quelle>` (5×: 4 Extracts + `user_input`) | `dags/bronze_to_silver_dag.py` (Meta-DAG) | `@continuous`; eigener Sensor `wait_for_new_bronze` prüft jede Minute die eigene Bronze-Tabelle | Initiative (Silber, versioniert) |
| `silver_to_gold` | `dags/silver_to_gold_dag.py` | `@continuous`; Sensor `wait_for_silver_changes` prüft jede Minute, ob ein Use Case fällig ist | AssessedInitiatives (Gold) |

1. **RawToBronze** — `SourceFileSensor` wartet auf eine neue/geänderte
   `2026?AI?Initiatives*.xlsx` (passt auf `2026_AI_Initiatives_Elia_Group.xlsx` in
   `data/sources/` und auf die Schreibweise mit Leerzeichen; Größe stabil, mtime neuer als die Marker-Datei
   `.ai_cockpit_import.last_processed`). Danach lädt je Quellblatt ein
   `RawToBronzeOperator` die Zeilen 1:1 als Text in seine Extract-Tabelle
   (`IT_Initiatives_Extract`, `50Hertz_Initiatives_Extract`,
   `CorporateOneSAP_Initiatives_Extract`, `ETB_Initiatives_Extract`).
   **Append-only:** Jeder Load hängt seine Zeilen an, mit `ID` (fortlaufend,
   in Blattreihenfolge), `Timestamp` (gleich für alle Zeilen eines Loads) und
   `SourceFileID` (Pfad der Quelldatei); frühere Loads bleiben. Hat ein Blatt
   selbst eine Spalte mit einem dieser Namen, bricht der Load ab. Leere Zeilen (ohne Name)
   werden übersprungen; fehlt eine Spalte des Datenmodells im Blatt, bricht
   der Task ab. Jeder Load-Task emittiert das Dataset seiner Tabelle.
2. **SeedConfig** — Config-Tabellen sind einmalig zu befüllende
   Konfiguration. Der DAG legt nur fehlende Einträge an (nie Update/Delete):
   SolutionType/ValueType aus dem Blatt `Variables`, RiskClassification mit
   den 5 Stufen der Rahmenbetriebsvereinbarung KI, Owner aus den
   Owner/Department-Paaren des jeweils letzten Loads (Category = Business Unit).
   Nach dem ersten `raw_to_bronze`-Lauf manuell starten, später erneut, wenn
   neue Owner oder Katalogeinträge dazukommen (Silber legt keine an).
3. **BronzeToSilver (Meta-DAG)** — `build_bronze_to_silver_dag()` erzeugt aus
   einem Template je Eintrag in `ai_cockpit_ingestion/sources.py` einen DAG
   `bronze_to_silver_<key>` (auch für `UserActionExtracts`). Jeder
   läuft `@continuous` (max. ein offener Lauf) mit eigenem Sensor
   `wait_for_new_bronze` (`operators/new_bronze_sensor.py`, Modus reschedule,
   alle 60 s, `AI_COCKPIT_BRONZE_POKE_SECONDS`): Er prüft nur die eigene
   Tabelle und meldet „neu“, wenn deren jüngster Datensatz (max `Timestamp`)
   neuer ist als der jüngste `BronzeTimestamp` eines erfolgreichen Laufs in
   `TransformationRun` (noch kein Lauf → neu). Jeder Lauf protokolliert sich
   dort (Technik-Tabelle, ohne FK): `BronzeTableName`, `DagRunID`,
   `StartedAt`, `FinishedAt`, `BronzeTimestamp` (= max `Timestamp`, ermittelt
   **vor** dem Lesen — während des Laufs geschriebene Datensätze sind damit
   beim nächsten Lauf „neu“), `Status` (`running` → `success` im selben Commit
   wie die Silber-Schreibvorgänge, sonst `failed`) und die Zähler `RowsRead`,
   `RowsInserted`, `RowsUpdated`, `RowsUnchanged`, `RowsDeactivated`,
   `RowsConflict`. Verglichen werden nur Bronze-Zeitstempel, keine Airflow-
   Metadaten. Nach 24 h ohne neue Daten wird der Sensor übersprungen
   (soft fail), der Lauf endet grün und der nächste beginnt. Der Hash-Delta-
   Check hält wiederholte Läufe idempotent. Der
   `BronzeToSilverOperator` normalisiert Status → Stage
   und Timing, verknüpft **nur bestehende** Config-Einträge (Unbekanntes
   bleibt NULL und wird geloggt), schätzt die Value-Attribute
   (`transforms/value_heuristic.py`) und die Risikostufe
   (`transforms/risk_heuristic.py`) und **upsertet** die Initiativen seiner
   Business Unit (siehe „Upsert-Strategie“). Eine neue Quelle braucht nur
   einen neuen `SourceConfig`-Eintrag.

Die Marker-Datei wird erst gesetzt, wenn alle vier Extrakte geladen sind.

## Upsert-Strategie (Silber)

Die Quellblätter haben keine Initiative-ID (`Number` ist eine
Zeilennummer-Formel `=ROW()-ROW(...)`, im Corporate-Blatt feste 1…n). Silber
erkennt „dieselbe Initiative“ deshalb über zwei SHA-256-Hashes
(`transforms/upsert_keys.py`). Normalisierung: trimmen, Whitespace inkl.
NBSP zusammenfassen, Zero-Width-Zeichen entfernen, NULL → "", Teile mit
`\x1f` verkettet.

- **KeyHash** (Identität) = Business Unit + Name (zusätzlich casefold).
- **RowHash** (Delta) = die Quellspalten, die in Silber einfließen: Name,
  Description, Owner, Department, Flagship, AI Layer, Status, Solution Type,
  Solution Feasibility, High-Level Cost Assessment, Expected Outcome und, wo
  vorhanden, Added Value, Value, Complexity, Timing start, Timing delivery.
  Nicht: Number, Strategic Link (ETB), Impediments, 2026, Kolom1, Lade-/ID-Spalten.

Silber ist **append-only und versioniert** (seit 11/2026): jede Änderung
hängt eine neue Version an (neue `ID`, gleiche `UseCaseID`), nichts wird
überschrieben. Die aktuelle Version eines Use Cases ist die mit der höchsten
`ID` (`models.current_versions()`); jede Version ist ein vollständiger Stand.

| Fall | Ergebnis |
| --- | --- |
| KeyHash neu | neuer Use Case (`UseCaseID` = max + 1), erste Version |
| KeyHash bekannt, RowHash anders (oder Use Case inaktiv) | neue Version: alle Werte inkl. Heuristiken neu, neue BusinessTransactionID |
| KeyHash bekannt, RowHash gleich | unchanged, nichts geschrieben |
| Use Case wird in der UI gepflegt (eine Version stammt aus einer User-Action) | `ui_owned`: übersprungen, weder neue Version noch Soft-Delete (zählt in `RowsConflict`) |
| Key im Load doppelt, gleicher RowHash | einmal übernommen, Warnung (heute ETB „AC_012 check reporting“) |
| Key im Load doppelt, unterschiedlicher RowHash | Konflikt: nicht übernommen, beide Zeilen geloggt, Use Case bleibt |
| aktiver Use Case fehlt im neuen Load | Soft-Delete: neue Version mit `IsActive = false` (Kopie, behält die BusinessTransaction); taucht er wieder auf, neue aktive Version desselben Use Cases |
| DAG-Parameter `force = true` | jeder bekannte Use Case wird neu berechnet, neue Version nur, wo sich das Ergebnis ändert |

Silber speichert statt der Risikostufe die **sechs Risiko-Antworten**; Gold
leitet daraus die Stufe ab. Für Blatt-Initiativen sind es die kanonischen
Antworten der geschätzten Stufe (`risk_heuristic.risk_answers_for_level`:
1 alles nein, 2 `ChangesEmployeeWorkflows`, 3 `EmployeePersonalData = yes`,
4 `DecisionsOnEmployees = automated`). `OperatingCosts` heißt in Silber
`RunningCosts`.

Eine Umbenennung ist damit „alte Initiative deaktiviert, neue angelegt“.
Weil der RowHash die Quelle hasht, wirkt ein später ergänzter Owner
(`seed_config`) erst bei einer Quelländerung oder mit `force`.

**BusinessTransaction** (`BusinessTransaction`: `ID`, `BronzeID`,
`BronzeTableName`): ein Eintrag je
Bronze-Zeile, aus der eine Version entstand, und je verarbeiteter User-Action
(auch unveränderte und abgelehnte, damit keine doppelt gelesen wird). Die
Version zeigt per `BusinessTransactionID` darauf: Initiative →
BusinessTransaction → Bronze-Zeile (`BronzeTableName`, `BronzeID`) →
`Timestamp`, `SourceFileID`. Unveränderte Blatt-Zeilen bekommen keinen
Eintrag, Soft-Delete-Versionen behalten den vorigen. RawToBronze schreibt keine
BusinessTransaction. Laufzähler (inserted, updated, unchanged, deactivated,
conflicts) stehen im Task-Log und als Rückgabewert (XCom).

**User-Actions (Bronze)** (`UserActionExtracts`, ersetzt
`UserInput_Initiatives_Extract`): eine Zeile je Aktion in der UI (schreibt das
Backend), `ActionType`:

- `create` (Formular 1, neue AI-Idee): `UseCaseID` leer, Pflichtfelder wie
  bisher; wird ein neuer Use Case mit Status `pending`. KeyHash = Business Unit
  des Owners + Name; schon vergeben → Konflikt.
- `update` (Formular 1 bearbeiten, Formular 2, Stage-Gate): nur die gesetzten
  Felder zählen, sie werden auf die aktuelle Version gelegt. Name und Business
  Unit sind unveränderlich (wird ignoriert, Warnung). Stage-Gates:
  `NeedsGateDate`, `ScopeGateDate`, `DeployGateDate`, `RetireGateDate`, ein
  Datum je Gate; ein Datum bis heute heißt passiert, ein späteres geplant. Die
  Zuordnung Stage ↔ Gate (Form-2-Excel: Scope-Gate vor PoC, Deploy-Gate vor
  Production) prüft das Backend beim Speichern; die Pipeline übernimmt die
  Daten so, wie sie kommen.
- `approve` (nur aus `pending`): `LeadID` Pflicht; `NeedsGateDate` wird das
  mitgeschickte Datum, sonst bleibt ein schon gesetztes, sonst der Zeitstempel
  der Freigabe.
- `reject` (nur aus `pending`): `Comment` Pflicht.

`bronze_to_silver_user_input` (`operators/user_input_to_silver.py`) liest nur
Datensätze ohne BusinessTransaction, in ID-Reihenfolge, und gibt jedem eine
(neue Version, unchanged oder Konflikt). Value-Buckets, Faktoren und Kosten
werden aus den Treibern **aller Aktionen des Use Cases zusammengeführt**
berechnet (spätere Werte gewinnen, `transforms/user_input_heuristic.py`,
Testfälle in `tests/fixtures/user_input_cases.json`, die Backend und UI teilen);
ein Update muss also nur geänderte Treiber mitschicken. `ActualCosts` =
`ActualCapex` + `ActualOpex`. Die erste User-Action auf einem Blatt-Use-Case
macht ihn „UI-owned“; der Blatt-Import lässt ihn danach in Ruhe. `force`
rechnet zusätzlich alle Use Cases mit User-Actions neu.

Typisiert und per CHECK/FK abgesichert: Stammdaten als IDs der Config-Tabellen
(`OwnerID`, `LeadID`, `ValueTypeID`, `SolutionTypeID`), `Stage` (10 Werte, inkl. `Retired`),
`DateStart`/`DateDelivery` als Quartal („Q2 2027“), die Value-Treiber je Hebel
(Anteile 0–1, leerer Hebel = 0), `EstimateBasis`, `DeliveryLikelihood`,
`SolutionComplexityScore` (1–9), `OneTimeCosts`, `OperatingCosts`, die
Risiko-Indikatoren nach Rahmenbetriebsvereinbarung KI und die Felder aus
Formular 2 (`AILayer`, `EnablingTeam`, `EUAIActClass`, `EUAIActRole`,
`WorksCouncilRiskClass`, `CapabilityDirection` mit festen Werten; KPIs,
Value Domain, Autonomy Level, Zielgruppen als Text; `SafetyComponent`,
`WorksCouncilApprovedAt`, `ExpectedUsers`, `MeasuredBenefits`, `ActualCapex`,
`ActualOpex`). `SourceFileID` ist immer `user-input`, `SubmittedBy` der
angemeldete Nutzer (in Silber `ChangedBy`).

**Gold** (`AssessedInitiatives`, `silver_to_gold`, `operators/silver_to_gold.py`,
Formeln in `transforms/gold.py`): eine Zeile je Use Case aus seiner aktuellen
Silber-Version, in place aktualisiert. Bewertet werden nur **vollständige**
Use Cases: alle vier Value-Buckets, `ConfidenceScore` und `DeliveryScore`,
die sechs Risiko-Antworten, `OneTimeCosts` und `RunningCosts` gesetzt. Fällig ist ein Use Case, wenn er gerade vollständig
wurde (noch keine Gold-Zeile), wenn es eine neuere Silber-Version gibt als die
bewertete (eines der Rechen-Attribute oder ein kopiertes Feld wie Status oder
Gate hat sich geändert) oder wenn sein laufzeitbasierter RealizedValue zuletzt
vor heute berechnet wurde.

- `PotentialValue` = Summe der Buckets × ConfidenceScore × DeliveryScore (€/Jahr)
- `RealizedValue` = `MeasuredBenefits` − `ActualCosts`, wenn echte Werte gemeldet
  sind; sonst nach `DateDelivery`: PotentialValue × Laufzeit − (OneTimeCosts +
  RunningCosts × Laufzeit), Laufzeit in Jahren seit Delivery; sonst leer
- `RiskClassificationID` aus den Antworten (gleiche Regeln wie das Formular)

Läufe stehen in `TransformationRun` mit `BronzeTableName = Initiative`.
`force` bewertet alle vollständigen Use Cases neu. Lokal gegen die Excel:
164 Use Cases bewertet, Potenzial ≈ 9,77 Mio. € (wie vorher), 23 mit
RealizedValue (ETB, Delivery-Quartal vorbei), zweiter Lauf liest nichts.

Mit `{"force": true}` triggern: `airflow dags trigger bronze_to_silver_it -c '{"force": true}'`
oder in der UI „Trigger DAG w/ config“. Der Sensor wartet dann nicht auf neue
Daten. Weil `@continuous` immer einen Lauf offen hat, startet der getriggerte
Lauf erst nach dem offenen; schneller geht es, den wartenden Sensor des
offenen Laufs in der UI auf „success“ zu setzen.

## Heuristiken (Schätzungen, keine Messwerte)

- **Value** (`value_heuristic.py`, „Heuristik v2: Buckets einzeln“ aus dem
  Thread *Nutzen-Quantifizierung*, 1:1 portiert aus `data/value_heuristic.py`):
  Jeder der vier Buckets wird mit seiner eigenen Value-Sizing-Formel
  gerechnet. Treiber: Value-Score → Reichweite, SolutionType-Familie →
  Wirkung je Fall, Flagship → Kosten je Fehler/Ereignis/Verzug. Hypothetischer
  Nutzen = Summe der Buckets; Potenzial = Summe × ConfidenceScore ×
  DeliveryScore. Gegen `data/value_estimates_heuristic.csv` geprüft:
  identisch für alle 160 Initiativen des alten EliaGroup-Blatts (Nutzen;
  die Kosten weichen seit 24.10.2026 bewusst ab, siehe unten).
- **Kosten sind Erwartungswerte** (Entscheidung 24.10.2026): Die geschätzten
  Einmal- und Betriebskosten werden wie der Nutzen mit dem `DeliveryScore`
  gewichtet, und abgeschrieben wird für alle Initiativen über **5 Jahre**
  (vorher 1 Jahr für Lizenzen, 5 für Plattformen, sonst 3). In `OneTimeCosts`
  und `OperatingCosts` steht damit *Kosten bei Lieferung × DeliveryScore*;
  die Kosten bei Lieferung sind `Wert / DeliveryScore`. Die Kosten/Jahr, die
  das Backend ableitet (`OneTimeCosts / DepreciationYears + OperatingCosts`),
  sind dadurch ohne Änderung dort delivery-gewichtet. Stand nach dem Lauf mit
  `force` (164 aktive Initiativen): Potenzial ≈ 9,77 Mio. €, Kosten ≈ 7,04
  Mio. €/Jahr (bei Lieferung ≈ 11,8 Mio. €), netto ≈ +2,73 Mio. €, 73
  Initiativen netto positiv.
- **Risiko** (`risk_heuristic.py`): Regelkette aus Name/Beschreibung/
  Expected Outcome/Added Value und SolutionType. Automatisierte
  Entscheidungen/Profilbildung über Beschäftigte → 4; Beschäftigtendaten,
  Leistungs-/Verhaltensauswertung → 3; Assistenten/Ticket-Routing → 2;
  technische Modelle ohne Personenbezug → 1; sonst 2. Stufe 5 wird nie
  geschätzt. Übereinstimmung mit `risiko/risk_classification_estimates.csv`:
  147 von 160 (alle Stufe-4-Fälle, 13 von 14 Stufe-3-Fällen).

## Datenbank

Interim weiter eine SQLite-Datei (`AI_COCKPIT_DB_PATH`). Tabellen- und
Spaltennamen sind exakt die des Datenmodells (PascalCase, z. B.
`Initiative.DateStart`, FK-Spalten `<Tabelle>ID`); im Python-Code heißen die
Attribute snake_case. `IsActive` steht noch nicht im Datenmodell. Weil jetzt mehrere
DAGs in dieselbe Datei schreiben, entfällt der frühere atomare
Datei-Tausch: Jeder Task schreibt in genau einer kurzen Transaktion
(Backend sieht bis zum Commit den alten Stand), parallele Schreiber warten
über das SQLite-Busy-Timeout (120 s). Tabellen legt `db.get_engine()`
idempotent an — neue Spalten in bestehenden Tabellen aber nicht: Eine DB
mit dem Schema vor der Upsert-Strategie muss einmal neu aufgebaut werden
(Datei löschen, `raw_to_bronze` → `seed_config` → `bronze_to_silver_*`).

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
    lineage.py                   # neuester Load einer Extract-Tabelle
    operators/
      source_file_sensor.py
      raw_to_bronze.py
      seed_config.py
      bronze_to_silver.py
    transforms/
      normalize.py               # Status-/Timing-/Komplexitäts-Normalisierung, Katalog-Matching
      value_heuristic.py
      risk_heuristic.py
      upsert_keys.py             # KeyHash / RowHash
  tests/test_transforms.py
  tests/test_upsert.py           # Hashes und Upsert gegen eine Temp-DB
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

## Deploy-Hinweise Lifecycle-Datenmodell (Stand 01.11.2026)

- **Nur zusammen mit dem angepassten Backend deployen**: das Backend liest
  heute `Initiative.RiskClassificationID`/`OperatingCosts` und schreibt in
  `UserInput_Initiatives_Extract`; beides ändert sich hier.
- **Neuer DAG `silver_to_gold`**: nach dem Deploy einmal aktivieren
  (`airflow dags unpause silver_to_gold`); ebenso die `bronze_to_silver_*`.
- **Migration automatisch** (`migrations/lifecycle_2026_11.py`, läuft in
  `db.get_engine`): erkennt das alte `Initiative` (ohne `UseCaseID`), kopiert
  `UserInput_Initiatives_Extract` als `create` nach `UserActionExtracts` (alte
  Tabelle bleibt), löscht Silber, leert `BusinessTransaction` und
  `TransformationRun` und legt die neuen Tabellen an. Die
  `bronze_to_silver_*`-DAGs bauen Silber danach aus Bronze neu auf; die
  Use Cases bekommen dabei neue `UseCaseID`s. Lokal verifiziert gegen die
  Excel: 164 Use Cases, zweiter Lauf und `force` nur „unchanged“.
  Eine Datenbank mit dem Lifecycle-Stand davor (`Stagegate` + `PassedAt`)
  bekommt die vier Gate-Daten: Silber und Gold per `ALTER TABLE`, befüllt aus
  dem alten Paar (die alten Spalten bleiben ungenutzt stehen);
  `UserActionExtracts` wird wegen der geänderten CHECKs neu angelegt und
  umkopiert.

## Deploy-Hinweise (Stand 25.10.2026)

- **Neue Tabellen** `UserInput_Initiatives_Extract` und `TransformationRun`
  legt der erste Task, der die DB öffnet, per `create_all` an (die Sensoren
  tun das in der ersten Minute). Keine Migration, bestehende Tabellen
  unverändert.
- **Neuer DAG `bronze_to_silver_user_input`**: Airflow legt neue DAGs
  pausiert an — nach dem Deploy einmal aktivieren
  (`airflow dags unpause bronze_to_silver_user_input` oder Schalter in der UI).
- **`@continuous` + Sensor**: Jeder `bronze_to_silver_<key>`-DAG hat immer
  einen offenen Lauf; `wait_for_new_bronze` prüft im Modus reschedule alle
  60 s (`AI_COCKPIT_BRONZE_POKE_SECONDS`). Mit dem KubernetesExecutor startet
  jede Prüfung einen Pod (5 DAGs → 5 kurze Pods pro Minute); bei Bedarf das
  Intervall erhöhen.
- **Erster Lauf nach dem Deploy**: `TransformationRun` ist leer, jeder Sensor
  meldet einmal „neu“ und transformiert den aktuellen Stand; der
  Hash-Delta-Check ändert dabei nichts (lokal verifiziert: nur „unchanged“).
- **Gemeinsame DB**: Das Backend schreibt neue Eingaben in
  `UserInput_Initiatives_Extract` (RWX-Volume, wie Airflow).

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

Für die laufende Verarbeitung `airflow scheduler` starten und die DAGs
aktivieren (`airflow dags unpause ...`). Läuft parallel ein anderer
Airflow, `AIRFLOW__LOGGING__WORKER_LOG_SERVER_PORT` umstellen (Standard 8793).

Beim allerersten Lauf starten die Silber-DAGs schon nach `raw_to_bronze` und
schlagen fehl, solange die Config leer ist. Deshalb die Silber-DAGs erst nach
`seed_config` aktivieren (oder danach einmal manuell triggern). Um eine
unveränderte Excel erneut zu laden, die Marker-Datei
`.ai_cockpit_import.last_processed` im Quellordner löschen.

## Verifiziert (23.10.2026, Airflow 2.10.2, Python 3.11, SQLAlchemy 1.4.54)

Lokal gegen `data/sources/2026_AI_Initiatives_Elia_Group.xlsx`, frische DB:

- Alle 6 DAGs laden ohne Import-Fehler; `pytest tests/`: 12 Tests grün (seit 24.10.2026: 13).
- Lauf 1: `raw_to_bronze` 165 Zeilen, `seed_config` 11/7/5/80,
  `bronze_to_silver_*` **164 inserted** (17 IT, 53 50Hertz, 29 Corporate,
  65 ETB): „AC_012 check reporting“ steht in ETB zweimal mit identischem
  Inhalt (eine Variante mit Leerzeichen am Ende) und wird einmal übernommen.
- Lauf 2 (unveränderte Excel, Marker gelöscht): Bronze verdoppelt (z. B.
  IT 34 Zeilen), Silber 164 × unchanged, alle IDs identisch.
- Lauf 3 (Kopie der Excel, im Blatt IT eine Zeile geändert, eine gelöscht,
  eine neu): IT 1 inserted, 1 updated, 15 unchanged, 1 deactivated; alle
  übrigen 163 IDs unverändert.
- `force = true` auf IT: 17 updated.
- Mit laufendem Scheduler starteten die Silber-DAGs wie bisher automatisch
  über die Datasets.

**Nicht lokal geprüft:** Installation über den Firmen-Spiegel und
`poetry.lock`, der `dependency_loader` im Cluster, das echte Plattform-Image.

Bekannte Datenlücken (Quelle, kein Code-Fehler): 23 Initiativen ohne Owner
in der Excel (22 ETB, 1 Corporate) → `owner_id` NULL; 102 mit Freitext statt
Katalog-SolutionType → `solution_type_id` NULL; 19 mit nicht erkanntem
Status → Stage `Unknown`.
