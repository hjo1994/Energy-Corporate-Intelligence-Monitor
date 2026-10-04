# AI Cockpit

Dashboard mit Übersicht über alle KI-Initiativen im Unternehmen — Owner, Status,
geschätzter Aufwand und Mehrwert je Initiative.

## Architektur

Drei separate Kubernetes-Deployments (siehe
[`solution documentation/Architecture.drawio`](solution%20documentation/Architecture.drawio)):

1. **`input-orchestration/`** — Airflow-DAG mit zwei Operatoren: File Sensor
   (wartet auf die Quell-Excel) und Raw-to-Silver-Operator (Reinigung/
   Type-Casting mit Polars, Schreiben in die DB).
2. **`backend/`** — FastAPI-Schnittstelle über SQLAlchemy auf die Datenbank.
   Generischer, read-only Lesezugriff, potenziell für mehrere Applikationen,
   nicht nur das Dashboard (Endpunkte: siehe `backend/README.md`).
3. **`frontend/`** — React-Dashboard, eigene Anwendung, konsumiert die
   Backend-API (Ansichten Matrix, Liste, Board; Details und Abweichungen vom
   Entwurf: `frontend/README.md`).

Datenmodell: siehe
[`solution documentation/Logical Data Model.drawio`](solution%20documentation/Logical%20Data%20Model.drawio)
(Entitäten `Initiative`, `Owner`, `SolutionType`, `ValueType`). Wird
ausschließlich vom Fachbereich gepflegt — Code folgt dem Diagramm, nicht
umgekehrt.

## Daten

- Prototyp-Datenbank: **SQLite** (Postgres ist für diesen Prototyp noch nicht
  verfügbar; der Wechsel ist nur ein SQLAlchemy-Connection-String).
- Quelle: Excel-Datei in `data/` (lokal, **nicht** versioniert — enthält
  Klarnamen von Owner:innen, siehe `.gitignore`).

### Bekannte Lücke Datenmodell ↔ Quell-Excel

Das Logical Data Model deckt nicht alle Spalten der Quell-Excel ab. Stand
nach Abstimmung mit dem Fachbereich:

**Geklärt:**
- `Source`/Business Unit **ist** abgebildet: `Owner.category` — die einzige
  owner-bezogene Gruppierung, die die Quelle hergibt, und genau das, was der
  Business-Unit-Filter im Dashboard braucht.
- **`ValueScore`/`SolutionComplexityScore` gehören zur einzelnen Initiative**,
  nicht zu `ValueType`/`SolutionType` — diese beiden Tabellen sind reine
  Referenz-/Lookup-Tabellen (Name + Description), **befüllt aus dem
  `Variables`-Sheet** (dem Katalog-Sheet der Quell-Excel), nicht aus den
  einzelnen Initiative-Zeilen.
- `SolutionType` ← `Solution Type`/`Solution Type description` aus
  `Variables`. **Nur 69 von 160 Initiativen (43 %)** haben einen
  `Solution Type`-Wert, der exakt einer der 11 Katalog-Kategorien entspricht
  — der Rest sind Freitext-Beschreibungen des Lösungsansatzes statt einer
  Kategorie-Auswahl. Entschieden: nur Katalog-Treffer verknüpfen,
  Freitext-Zeilen bekommen `solution_type_id = NULL` statt falsch
  einsortiert zu werden.
- `ValueType` ← `Flagship`/`Flagship description` aus `Variables`. Sehr
  sauber: 156/160 Treffer (der Katalog enthält 7 Einträge, darunter ein
  kurioser `"-"`-Eintrag und ein Eintrag mit einem unsichtbaren Zeichen im
  Variables-Sheet selbst — `"Connection lif﻿ecycle"` — die Zuordnung
  normalisiert das beim Abgleich, ohne den Katalog-Namen selbst zu ändern).
- `Timing start`/`Timing delivery` → `Initiative.date_start`/`date_delivery`
  (siehe Einschränkung unten — keine echten Datumswerte in der Quelle).

**Weiterhin nicht übernommen** (TODO im Code): `Impediments`,
`High-Level Cost Assessment`, `Expected Outcome`, `Added Value`,
`Strategic Link`, `Strategic Link ETB` (seit `ValueType` auf `Flagship`
umgestellt wurde, ohne eigenes Zielfeld), `2026` (nur 13/160 Zeilen befüllt,
uneinheitlich: `"x"`, `"yes"`, teils ganze Sätze wie "yes, if resources are
available (e.g., via Delaware / Copilot agents...)" — eher Freitext-Notiz
als strukturiertes Feld).

**Einschränkung bei `date_start`/`date_delivery`:** Die Quelle enthält nie
echte Datumswerte, nur Quartalsangaben (`"Q1"`–`"Q4"`, fast ausschließlich
bei ETB-Zeilen — nur 32 von 160 Initiativen haben überhaupt eine Angabe) und
einmal ein nacktes Jahr (`"2027"`) ohne Quartal. Ohne Jahresangabe pro Zeile
wird für jedes Quartal das Planungsjahr der Datei angenommen (`2026`,
`AI_COCKPIT_PLANNING_YEAR`) — eine Annahme, die bei der einen `"2027"`-Zeile
nachweislich nicht für alle Initiativen stimmt. Entspricht einem groben
Platzhalter, keinem verbindlichen Termin.

**Bewusst zurückgestellt** (Konsolidierung der Business Units und
Verknüpfung fehlender Owner folgt später; bis dahin wird eingelesen, was
zuordenbar ist, alles andere bleibt `NULL`): 22 von 160 Initiativen haben in
der Quelle keinen Owner und damit auch keine Business Unit; ein Owner
(gleicher Name + Department) steht in zwei Business Units (ETB und IT) und
trägt nur die BU der ersten Zeile; `Solution Type`-Schreibvarianten
(`"Co-pilot"` statt `"Copilot"`) werden bei striktem Katalogabgleich nicht
erkannt.

**Echte Datenlücke (keine Mapping-Frage):** `Initiative.value_score` ist für
**IT und Corporate & OneSAP+ durchgehend NULL** — diese beiden Units
erfassen gar keinen Mehrwert-Score in der Quelle (nur 66 von 160 Initiativen
insgesamt haben einen Score). Das Dashboard muss einen "kein Wert
erfasst"-Zustand abbilden, nicht nur eine Zahl.

### Interim-Entscheidung: SQLite-Datei geteilt zwischen zwei Deployments

Input Orchestration (Writer) und Backend (Reader) sind separate Deployments,
teilen sich aber übergangsweise eine SQLite-Datei auf einem RWX-Volume — bis
die echte Datenbank bereitsteht.

**Bekanntes Risiko:** SQLite-Dateien auf Netzwerk-Storage (NFS/SMB, wie die
RWX-StorageClasses im Zielcluster), von mehr als einem Pod gleichzeitig
geöffnet, können korrumpieren — SQLites Locking (`flock`/`fcntl`) ist auf
solchen Dateisystemen nicht zuverlässig. Bewusst in Kauf genommen für die
Übergangsphase, mit folgenden Mitigationen:

- Nur Input Orchestration schreibt; Backend öffnet die Datei **read-only**
  (Volume-Mount `readOnly: true`).
- **Kein WAL-Modus** (Default-Rollback-Journal) — WAL braucht verlässliches
  `mmap`, das auf Netzwerk-Storage nicht gegeben ist.
- Input Orchestration schreibt pro Lauf in eine neue Datei und ersetzt die
  aktive Datei per atomarem `rename()` — kein Dauerschreiben auf die von
  Backend gelesene Datei.
- `replicas: 1` für Input Orchestration (immer nur ein Writer).
- Backend behandelt `database is locked` / `disk I/O error` mit Retry.

**Migrations-Trigger:** Sobald die echte Datenbank verfügbar ist, mehr als
eine Input-Orchestration-Replika nötig wird, oder Lock-/Korruptionsfehler
auftreten — Wechsel ist nur ein SQLAlchemy-Connection-String, kein Code-Eingriff.

## Deployment

Ziel: gleiche Kubernetes-Infrastruktur wie vorherige Projekte (siehe `infra/`).
