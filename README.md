# AI Initiatives Cockpit

Dashboard mit Übersicht über alle KI-Initiativen im Unternehmen — Owner, Status,
geschätzter Aufwand und Mehrwert je Initiative.

## Architektur

Drei separate Kubernetes-Deployments (siehe
[`solution documentation/Architecture.drawio`](solution%20documentation/Architecture.drawio)):

1. **`input-orchestration/`** — Airflow-DAGs im Bronze/Silber-Aufbau:
   `raw_to_bronze` (File Sensor + 1:1-Load der vier Quellblätter in die
   Extract-Tabellen), `seed_config` (einmaliges Befüllen der Config-Tabellen)
   und der Meta-DAG `bronze_to_silver`, der je Extract-Tabelle einen DAG
   erzeugt (Normalisierung, Value- und Risiko-Heuristik, Schreiben in
   Initiative). Details: `input-orchestration/README.md`.
2. **`backend/`** — FastAPI-Schnittstelle über SQLAlchemy auf die Datenbank.
   Generischer, read-only Lesezugriff, potenziell für mehrere Applikationen,
   nicht nur das Dashboard (Endpunkte: siehe `backend/README.md`).
3. **`frontend/`** — React-Dashboard, eigene Anwendung, konsumiert die
   Backend-API (Ansichten Matrix, Liste, Board; Details und Abweichungen vom
   Entwurf: `frontend/README.md`).
