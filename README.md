# AI Initiatives Cockpit

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
