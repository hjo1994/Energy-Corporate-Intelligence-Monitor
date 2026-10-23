# Backend — FastAPI + SQLAlchemy

Eigenes Kubernetes-Deployment. Stellt die Daten aus der DB über eine
**read-only** REST-API bereit — generischer Lesezugriff, nicht exklusiv ans
Dashboard gebunden; potenziell mehrere Applikationen als Konsumenten. Kein
Schreibpfad.

## Endpunkte

| Endpunkt | Zweck |
|---|---|
| `GET /api/healthz` | Liveness, ohne Auth, prüft nicht die DB. Kein `/startup`/`/readz`: das Referenz-Deployment konfiguriert keine Probes |
| `GET /api/auth/rights` | angemeldeter Nutzer und seine Rechte (für das Frontend) |
| `GET /api/initiatives` | Liste; Filter `stage`, `business_unit`, `department`, `risk_classification_id` (mehrfach angebbar), `owner_id`, `solution_type_id`, `value_type_id`, `search` (Substring in Name/Description); `sort` (`name`, `stage`, `potential_value_eur`, `hypothetical_value_eur`, `annual_cost_eur`, `solution_complexity_score`, `risk_classification`, `date_start`, `date_delivery`), `order`, `limit` (1–500, Default 50), `offset`. Antwort `{items, total, limit, offset}` mit verschachteltem `owner`/`solution_type`/`value_type`/`risk_classification` (id, name) |
| `GET /api/initiatives/{id}` | Einzelne Initiative |
| `GET /api/initiatives/summary` | Gesamtzahl, Anzahl je Stage und je Risikostufe, Summe/Ø Potenzial, Summe hypothetischer Nutzen und Kosten/Jahr, Ø Komplexität, Anzahl ohne Owner |
| `GET /api/owners` | Owner (optional `business_unit`) |
| `GET /api/business-units` | Distinkte `Owner.category` mit Initiativen-Anzahl |
| `GET /api/stages` | Stage-Werte mit Anzahl |
| `GET /api/risk-classifications` | Die 5 Risikostufen der Rahmenbetriebsvereinbarung KI (auch ungenutzte) mit Beschreibung und abgeleiteten Maßnahmen |
| `GET /api/solution-types`, `GET /api/value-types` | Lookup-Kataloge |

### Felder einer Initiative

Gespeichert (von der Input Orchestration geschätzt, siehe deren README):
`stage`, die vier Nutzen-Buckets `efficiency_score_eur`, `quality_score_eur`,
`risk_reduction_score_eur`, `strategic_value_score_eur` (€/Jahr), die
Abschläge `confidence_score` und `delivery_score`,
`solution_complexity_score`, `one_time_costs`, `operating_costs` (€/Jahr),
`depreciation_years`, `risk_classification`.

Abgeleitet (nicht gespeichert, `app/derived.py`, in SQL für Sortierung/Summary
und in Python für die Antwort):

- `hypothetical_value_eur` = Summe der vier Buckets
- `potential_value_eur` = hypothetischer Nutzen × Confidence × Delivery — der
  „Mehrwert“, den das Dashboard zeigt
- `annual_cost_eur` = einmalige Kosten / Abschreibungsjahre + Betriebskosten

Fehlt ein Eingangswert, ist der abgeleitete Wert `null` (nie 0).

Interaktive Doku: `/docs` (Swagger UI; lädt aktuell noch von einem CDN und
bleibt im Cluster leer — Offline-Variante steht noch aus).

## Authentifizierung

Übernommen aus dem Digital-Lab-Portal: `eg-auth` mit `authorizer()` als
Router-Abhängigkeit (`app/auth.py`), alle Daten-Endpunkte verlangen einen
angemeldeten Nutzer, `/api/healthz` nicht. Gesteuert über `EG_AUTH_DEV_MODE`
und `EG_AUTH_DEV_GROUPS` (siehe `.env.example`).

- **Im Cluster:** `eg-auth` (Extra `fastapi`, Version wie Referenz-App) kommt
  vom Firmen-Spiegel und muss in der Poetry-`pyproject.toml` stehen;
  `EG_AUTH_DEV_MODE=False`. Dann prüft das echte Paket das OIDC-Token.
- **Lokal:** `local_stubs/eg_auth` (Kopie aus dem Digital-Lab-Portal) mit
  `PYTHONPATH=local_stubs` und `EG_AUTH_DEV_MODE=True`. Der Stub kann nur den
  Dev-Modus und verweigert sonst mit 401. **`PYTHONPATH` darf im Deployment
  `local_stubs` nie enthalten**, siehe `local_stubs/README.md`.
- **Rechte:** Aktuell genügt Anmeldung. `canViewInitiatives` wird von einer
  Platzhaltergruppe aus dem Template abgeleitet und ist nur informativ, bis
  die echte Gruppe feststeht (TODO in `app/auth.py`).
- **Frontend:** meldet per OIDC an (`eg-auth-react`) und schickt den Token als
  Bearer-Header; lokal läuft alles im Dev-Modus (Bypass im Frontend, siehe
  `frontend/README.md`).
- Getestet ist das gegen den **Stub**: Gating, 401 ohne Anmeldung, Rechte aus
  Gruppen. Das Verhalten des echten `eg-auth` ist nicht geprüft.

`business_unit` = `Owner.category`. **Initiativen ohne Owner (aktuell 23 von
165) gehören damit zu keiner Business Unit** und tauchen in BU-Filter und
`/api/business-units` nicht auf — bis die Owner-Verknüpfung nachgezogen wird.
Die BU-Werte kommen unverändert aus der Quelle (z. B. `"50 Hertz"`,
`"Corporate"`). Scores sind bei vielen Initiativen `null`; bei `sort` stehen
`null`-Werte immer am Ende (portabel über `IS NULL`, nicht `NULLS LAST`: SQLite
3.26 im Cluster-Image und MySQL kennen das nicht).

## Verhalten gegenüber der geteilten SQLite-Datei

Siehe Interim-Entscheidung im Root-README. Konkret umgesetzt:

- Die Datei wird auf SQLite-Ebene `mode=ro` geöffnet (zusätzlich zum
  read-only Volume-Mount).
- **Kein Connection-Pool** (`NullPool`): Jede Anfrage öffnet die Datei neu
  und sieht damit sofort, was die DAGs committet haben (sie schreiben in
  kurzen Transaktionen direkt in die Datei). Auch ein Austausch der Datei
  per Rename (z. B. Backup einspielen) wird erkannt. Beides getestet.
- Schlägt das Öffnen fehl (z. B. während ein DAG schreibt), 3 Versuche mit
  kurzem Backoff, danach `503` + `Retry-After`.

## Struktur

```
backend/
  pyproject.toml     # Poetry-Format (Cluster-Build)
  requirements-local.txt   # nur lokal, ohne Poetry/Spiegel
  app/
    main.py          # get_app() — mit uvicorn als Factory starten
    auth.py          # eg-auth: Rights, authorizer(), /api/auth/rights
    config.py        # AI_COCKPIT_DB_PATH (Default /data/db/ai_cockpit.db)
    db.py            # read-only Engine, Session mit Retry
    models.py        # Kopie der Silber-/Config-Modelle aus input-orchestration (von Hand synchron halten)
    derived.py       # abgeleitete Werte: hypothetischer Nutzen, Potenzial, Kosten/Jahr
    schemas.py
    api/initiatives.py, api/reference.py
  local_stubs/       # eg-auth-Stub nur für lokale Entwicklung
  tests/             # synthetische Test-DB, keine echten Daten
```

`app/models.py` ist eine von Hand gepflegte Kopie von
`input-orchestration/ai_cockpit_ingestion/models.py` (separate Images, kein
gemeinsames Paket). Das Datenmodell selbst pflegt ausschließlich der
Fachbereich im drawio.

## Deployment (Plattform)

Die Plattform baut per S2I (Python/Poetry 1.8), nicht per Dockerfile:

- `pyproject.toml` im Poetry-Format wie das Template (`package-mode = false`,
  Spiegel `50hertzPublic` als primäre Quelle, Versionen wie im Template).
  **Die `poetry.lock` fehlt noch** und muss im Firmennetz mit Poetry 1.8.5
  erzeugt werden (`poetry lock --no-update`, danach `poetry check --lock`);
  Poetry 2.x schreibt ein Format, das das Basisimage nicht liest.
- Startkommando (Umgebungsvariable `COMMAND`):
  `uvicorn app.main:get_app --factory --host 0.0.0.0 --port 8000`
- ConfigMap: `AI_COCKPIT_DB_PATH` (Pfad der geteilten Datei, Volume
  read-only), `EG_AUTH_DEV_MODE=False`. **`PYTHONPATH` darf nicht gesetzt
  sein oder `local_stubs` enthalten.**
- Keine Probes im Referenz-Deployment; `/api/healthz` steht trotzdem bereit.
- Alles, was die App zur Laufzeit liest, muss unter `backend/` liegen (der
  Build sieht nur diesen Ordner) — aktuell nur die DB-Datei vom Volume.

## Lokal starten

Ohne Poetry und ohne Firmen-Spiegel (nicht erreichbar): `requirements-local.txt`
spiegelt die Abhängigkeiten aus `pyproject.toml` in den Template-Versionen
(ohne `eg-auth`, das ersetzt der Stub). Beim Ändern der Abhängigkeiten beide
Dateien pflegen; der Cluster-Build nutzt nur `pyproject.toml` + `poetry.lock`.

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements-local.txt
EG_AUTH_DEV_MODE=True PYTHONPATH=local_stubs \
AI_COCKPIT_DB_PATH=../input-orchestration/.airflow_home/ai_cockpit.db \
  .venv/bin/uvicorn app.main:get_app --factory --port 8000
.venv/bin/python -m pytest
```

Verifiziert (23.10.2026): 20 Tests (Filter inkl. Risikostufe, Suche inkl.
`%`/`_`-Escaping, abgeleitete Werte, Sortierung mit NULLs, Paginierung,
Summary, Read-only, neue Commits des Writers und Datei-Austausch per Rename
sichtbar, 503 bei fehlender DB, Auth, portables SQL, Startkommando der
Plattform) sowie ein Lauf gegen die echte Datenbank mit identischen Zahlen
wie der DAG-Lauf (165 Initiativen, ≈ 9,8 Mio. € Potenzial, ≈ 39,8 Mio. €
hypothetisch, ≈ 15,6 Mio. € Kosten/Jahr). Nicht getestet: Zugriff über ein RWX-Volume aus einem
getrennten Pod.
