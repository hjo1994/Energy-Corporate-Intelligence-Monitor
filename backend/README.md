# Backend — FastAPI + SQLAlchemy

Eigenes Kubernetes-Deployment. Stellt die Daten aus der DB über eine
REST-API bereit — generischer Lesezugriff, nicht exklusiv ans Dashboard
gebunden; potenziell mehrere Applikationen als Konsumenten. Schreibpfade: `POST /api/initiatives` (Formular 1), `PATCH /api/use-cases/{id}`
(Formular 1 bearbeiten, Formular 2, Stage und Gate-Daten) und `POST /api/use-cases/{id}/decision`
(Genehmigung) schreiben je eine User-Action in die
Bronze-Tabelle `UserActionExtracts`; alle anderen Endpunkte lesen
über eine read-only-Verbindung. Im Cluster braucht das Backend dafür
Schreibzugriff auf die DB: das geteilte RWX-Volume ohne `readOnly` mounten
(wie bei Airflow, das dieselbe Datei beschreibt). Das Backend schreibt
ausschließlich in `UserActionExtracts`.

## Endpunkte

Pfade mit `{id}` meinen die **UseCaseID** (stabil über alle Versionen). Eine
Idee, die die Pipeline noch nicht verarbeitet hat, hat `id` = −Record-ID: lesbar,
aber noch nicht änder- oder entscheidbar (`409`).

| Endpunkt | Zweck | Recht |
|---|---|---|
| `GET /api/healthz` | Liveness, ohne Auth, prüft nicht die DB | – |
| `GET /api/auth/rights` | angemeldeter Nutzer und Rechte `canViewInitiatives`, `canApprove`, `canAdmin` | angemeldet |
| `GET /api/initiatives` | Dashboard-Liste: aktuelle Silber-Version je Use Case mit Gold-Werten. Filter `stage`, `business_unit`, `department`, `risk_classification_id` (Gold), `approval_status`, `owner_id`, `solution_type_id`, `value_type_id`, `search`; `sort` (`name`, `stage`, `potential_value_eur`, `realized_value_eur`, `hypothetical_value_eur`, `annual_cost_eur`, `solution_complexity_score`, `risk_classification`, `date_start`, `date_delivery`), `order`, `limit` (1–500), `offset`, `include_inactive`, `include_pending` | angemeldet |
| `GET /api/initiatives/summary` | Kennzahlen; Potenzial, realisierter Wert und Risiko aus Gold, dazu `not_assessed` | angemeldet |
| `GET /api/initiatives/{id}` | ein Use Case im Dashboard-Format | angemeldet |
| `POST /api/initiatives` | **Formular 1**: neue AI-Idee → User-Action `create`. `ai_layer` statt Solution Type, `running_cost_range` (`up_to_10k`, `10k_to_50k`, `50k_to_100k`, `over_100k`; gespeichert als 5k/30k/75k/150k €/Jahr) statt Betriebskosten. Alle Zahlen nur aus ihrem Wertebereich (`value_domains`, sonst `422`); Gate-Daten passend zur Stage (siehe unten). `201` als `pending`, `409` bei gleichem Namen in derselben Business Unit | angemeldet |
| `GET /api/me/use-cases` | **Meine Use Cases**: eingereicht, Owner oder Lead (Abgleich über `Owner.Email`, sonst Name), mit `roles`, `todos` (`complete_details`, `revise_and_resubmit`), `form2_progress` | angemeldet |
| `GET /api/use-cases/{id}` | alle Felder aus Formular 1 und 2, Gold-Werte, eingegebene Treiber (`drivers`), `revision`, `can_edit`, `can_decide`, `todos` | angemeldet |
| `PATCH /api/use-cases/{id}` | Teilupdate → User-Action `update`. `base_revision` Pflicht (`409`, wenn inzwischen geändert); `name`/Business Unit `422`; Beschreibung und Kostenschätzungen (`one_time_costs`, `running_cost_range`) nach dem Einreichen `422`, außer beim Überarbeiten einer abgelehnten Idee; die Stage nie unter die aus Formular 1 (`stage_floor`, `422`); Formular 2, Stage und Gate-Daten sonst jederzeit, auch vor der Genehmigung. Wird `stage` oder ein Gate-Datum geschickt, müssen Stage und Gate-Daten zusammen passen (`422`); `resubmit: true` schickt eine abgelehnte Idee zurück in `pending` | Einreicher, Owner, Lead, Admin |
| `GET /api/approvals` | **Approver-Inbox**: offene Ideen, älteste zuerst | `canApprove` |
| `POST /api/use-cases/{id}/decision` | `approve` (mit `lead_id`; setzt das Needs-Gate-Datum auf heute, außer der Einreicher hat schon ein vergangenes angegeben, und nie nach einem später passierten Gate) oder `reject` (mit `comment`) → User-Action `approve`/`reject`; nur aus `pending` | `canApprove` |
| `GET /api/use-cases/{id}/similar` | Re-use-Check: aktive Use Cases mit der größten Wortüberschneidung in Name und Beschreibung | `canApprove` |
| `GET /api/form-options` | Auswahllisten für Formular 1 und 2, dazu `stage_gate_rules` und `value_domains` (Wert + Label je Zahlenfeld von Formular 1) | angemeldet |
| `GET /api/owners` | Owner, optional `business_unit`, `search` (Name, Abteilung, E-Mail), `limit` | angemeldet |
| `GET /api/features` | Feature-Schalter `initiative_input` (`AI_COCKPIT_ENABLE_INITIATIVE_INPUT`; `false` sperrt alle Schreibpfade mit `403`) | angemeldet |
| `GET /api/business-units`, `/api/stages`, `/api/risk-classifications`, `/api/solution-types`, `/api/value-types` | Lookups (Zählungen über die aktuellen, aktiven Versionen) | angemeldet |

### Felder eines Use Cases

Aus der aktuellen Silber-Version: `stage`, die vier Nutzen-Buckets (€/Jahr),
`confidence_score`, `delivery_score`, `solution_complexity_score`,
`one_time_costs`, `running_costs` (€/Jahr; `operating_costs` liefert denselben
Wert, bis die UI umgestellt ist), `depreciation_years`, Status, die Gate-Daten
`needs_gate_date`, `scope_gate_date`, `deploy_gate_date`, `retire_gate_date`
und daraus `last_gate` (das späteste Gate mit Datum bis heute).
Aus Gold (`AssessedInitiatives`): `potential_value_eur`, `realized_value_eur`,
`risk_classification`. Abgeleitet (`app/derived.py`):
`hypothetical_value_eur` (Summe der Buckets) und `annual_cost_eur` (einmalige
Kosten / Abschreibungsjahre + laufende Kosten).

**Stage und Stage-Gates** (`app/lifecycle.py`): ein Datum je Gate, bis heute
= passiert, später = geplant. Regel aus der Form-2-Excel („scope gate must be
passed before PoC, deploy gate must be passed before production“):
Idea/Exploration – Scope und Deploy noch nicht passiert; PoC/MVP/Implementation –
Scope passiert, Deploy noch nicht; Production/Retired – Scope und Deploy
passiert; On hold/Cancelled/Unknown – keine Regel. Gesetzte Daten in
Gate-Reihenfolge. Für Needs und Retire nennt die Excel keine Regel. Reihenfolge der Stages: Idea → Exploration → PoC → MVP → Implementation → Production → Retired (`stage_order` in `/api/form-options`); On hold, Cancelled und Unknown stehen außerhalb. Passt ein
Stand nicht (etwa ein Use Case aus dem Blatt in Production ohne Daten), steht
das in `stage_problems`; andere Änderungen blockiert das nicht.

**Noch nicht verarbeitet:** Jede Änderung geht zuerst nach Bronze; Silber und
Gold folgen nach den DAG-Läufen (je etwa eine Minute). Die Endpunkte legen
unverarbeitete User-Actions deshalb über den aktuellen Stand, so wie der DAG
sie anwenden wird (`app/use_cases.py`), und markieren das in `processing`:
`pending` (neue Idee, noch nicht in Silber), `changes_pending` (Änderungen
unterwegs), `not_assessed` (Gold hat die aktuelle Version noch nicht bewertet,
etwa weil sie unvollständig ist) oder `assessed`. Solange nicht `assessed`,
sind Potenzial und Risiko vorläufig berechnet (`provisional: true`, gleiche
Formeln, geprüft gegen `tests/fixtures/user_input_cases.json`). Fehlt die
Tabelle `UserActionExtracts` noch, gibt es keine Pending-Einträge und die
Schreibpfade antworten `503`; ist die DB für das Backend read-only, ebenfalls.

Interaktive Doku: `/api/docs` (Swagger UI offline aus `swagger-ui-bundle`,
`app/docs.py`), Schema unter `/api/openapi.json`.

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
- **Rechte:** Lesen und Einreichen verlangt nur Anmeldung. `canApprove`
  (Inbox, Entscheidung, Re-use-Check) und `canAdmin` (darf jeden Use Case
  bearbeiten, darf auch genehmigen) kommen aus AD-Gruppen, die je
  Installation gesetzt werden: `AI_COCKPIT_APPROVER_GROUPS` und
  `AI_COCKPIT_ADMIN_GROUPS` (kommagetrennt; leer = niemand).
  `canViewInitiatives` wird weiter von einer Platzhaltergruppe abgeleitet und
  ist nur informativ (TODO in `app/auth.py`).
- **Frontend:** meldet per OIDC an (`eg-auth-react`) und schickt den Token als
  Bearer-Header; lokal läuft alles im Dev-Modus (Bypass im Frontend, siehe
  `frontend/README.md`).
- Getestet ist das gegen den **Stub**: Gating, 401 ohne Anmeldung, Rechte aus
  Gruppen. Das Verhalten des echten `eg-auth` ist nicht geprüft.

`business_unit` = `Owner.category`. **Use Cases ohne Owner (Stand Excel-Import 23 von
165) gehören damit zu keiner Business Unit** und tauchen in BU-Filter und
`/api/business-units` nicht auf — bis die Owner-Verknüpfung nachgezogen wird.
Die BU-Werte kommen unverändert aus der Quelle (z. B. `"50 Hertz"`,
`"Corporate"`). Scores sind bei vielen Initiativen `null`; bei `sort` stehen
`null`-Werte immer am Ende (portabel über `IS NULL`, nicht `NULLS LAST`: SQLite
3.26 im Cluster-Image und MySQL kennen das nicht).

## Verhalten gegenüber der geteilten SQLite-Datei

Siehe Interim-Entscheidung im Root-README. Konkret umgesetzt:

- Lesende Endpunkte öffnen die Datei auf SQLite-Ebene `mode=ro`. Nur die
  drei Schreibpfade nutzen eine schreibende Verbindung (ausschließlich für
  `UserActionExtracts`); das Volume ist dafür ein RWX-Volume ohne
  `readOnly`.
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
    db.py            # read-only Engine (+ Schreib-Engine nur für POST), Session mit Retry
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
  `poetry.lock` ist im Firmennetz mit Poetry 1.8.5 erzeugt; bei Änderungen an
  den Abhängigkeiten dort neu erzeugen (`poetry lock --no-update`, danach
  `poetry check --lock`). Poetry 2.x schreibt ein Format, das das Basisimage
  nicht liest.
- Startkommando (Umgebungsvariable `COMMAND`):
  `uvicorn app.main:get_app --factory --host 0.0.0.0 --port 8000`
- ConfigMap: `AI_COCKPIT_DB_PATH` (Pfad der geteilten Datei, RWX-Volume ohne
  `readOnly`), `EG_AUTH_DEV_MODE=False`, optional
  `AI_COCKPIT_ENABLE_INITIATIVE_INPUT` (Default `true`; `false` nur als
  Notbremse, schaltet die Eingabemaske ab). **`PYTHONPATH` darf nicht gesetzt
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

Verifiziert (23.10.2026): 21 Tests (Filter inkl. Risikostufe, Soft-Delete, Suche inkl.
`%`/`_`-Escaping, abgeleitete Werte, Sortierung mit NULLs, Paginierung,
Summary, Read-only, neue Commits des Writers und Datei-Austausch per Rename
sichtbar, 503 bei fehlender DB, Auth, portables SQL, Startkommando der
Plattform) sowie ein Lauf gegen die echte Datenbank mit identischen Zahlen
wie der DAG-Lauf (165 Initiativen, ≈ 9,8 Mio. € Potenzial, ≈ 39,8 Mio. €
hypothetisch, ≈ 15,6 Mio. € Kosten/Jahr). Nicht getestet: Zugriff über ein RWX-Volume aus einem
getrennten Pod.
