# Frontend — React Dashboard

Eigenes Kubernetes-Deployment, eigene Anwendung. Konsumiert ausschließlich die
Backend-API (`/api/...`); kein eigener Datenzugriff. Geschrieben wird nur über die
Lifecycle-Endpunkte (Formular 1, Formular 2, Entscheidung), die im Backend als
User-Actions in Bronze landen.
React 18 + Vite + TypeScript (Versionen wie das Plattform-Template, damit sie
der Firmen-Spiegel führt; mit diesen Versionen getestet), Schrift (IBM Plex)
als Dateien im Repo (`src/fonts/`, OFL-Lizenzen liegen bei; bewusst keine
npm-Pakete, die der Firmen-Spiegel eventuell nicht führt), keine externen
Requests zur Laufzeit.

## Ansichten (nach den abgenommenen Entwürfen)

**Sprache der Oberfläche: Englisch** (alle sichtbaren Texte, Fehlermeldungen, `lang="en"`,
Route `/list`). Die Texte stehen direkt in den Komponenten, es gibt bewusst keine
i18n-Bibliothek; eine zweite Sprache wäre ein eigener Schritt. Die Meldungen im
JSON-Body des Backends (`detail`) sind noch deutsch, das Frontend zeigt sie aber
nicht an, sondern eigene Texte je HTTP-Status.

- **Matrix** (`/`) — Aufwand × Potenzial als Quadranten-Plot, KPI-Kacheln,
  Detailpanel zur angeklickten Initiative. Darunter das **Topics-Widget** (in den Daten `ValueType`, früher „Flagship“):
  je strategischer Säule Anzahl und Summe des geschätzten Potenzials (und wie
  viele Initiativen darin überhaupt geschätzt sind). Es folgt den übrigen Filtern; ein Klick auf eine Zeile filtert über alle
  Ansichten nach diesem Topic. Initiativen ohne Topic stehen als eigene
  Zeile „Not assigned“, damit die Summe stimmt; „No topic“ ist der
  Katalogeintrag `-`.
- **List** (`/list`) — sortierbare Tabelle (inkl. Potenzial und Risikostufe), Filter links (Stage,
  Business Unit, Topic), Klick auf den Namen öffnet die Details.
- **Board** (`/board`) — Spalten je Stage, Karten mit Owner, Aufwand,
  Potenzial; Klick öffnet die Details.
- **Value** (`/value`) — drei Wert-Ansichten nach den Entwürfen A, B und G
  (Canvas „Value-Visualisierung Entwürfe“), alle auf den gefilterten
  Initiativen (Business Unit und Stage oben), alle als Schätzung
  (Heuristik v2) gekennzeichnet:
  - **Value bridge** — Wasserfall in M €/Jahr: hypothetischer Nutzen →
    Confidence-Abschlag → Delivery-Abschlag → Potenzial → Kosten/Jahr → Netto
    (negativ: gestrichelter Balken unter null). Daneben Confidence-Abschlag in %
    und „Net positive x / n“ mit den Netto-Summen; darunter das Potenzial je
    Nutzen-Bucket (Bucket × Confidence × Delivery). Gezählt werden nur
    Initiativen mit Potenzial und Kosten; fehlen welche, nennt die Legende sie.
  - **Break-even map** — je Initiative Kosten/Jahr (x) gegen Potenzial (y),
    k €; gestrichelte Diagonale Potenzial = Kosten, Fläche darüber getönt.
    Die Kosten-Heuristik arbeitet in Stufen, darum werden die Punkte
    deterministisch um bis zu 8 px seitlich versetzt. Chips nach Stage-Gruppe
    (Ideation / PoC & MVP / Implementation & Production / Unclear,
    paused = On hold, Cancelled, Unknown) blenden die übrigen Punkte ab; die
    Kennzahlen (über Break-even, Netto-Summe) folgen der Auswahl. Tooltip bei
    Hover/Fokus, Klick öffnet den Detaildialog.
  - **Value roadmap** — Potenzial je Lieferquartal (`date_delivery`) als
    Balken plus kumulierte Linie, leere Quartale dazwischen bleiben als Lücke
    stehen; daneben schraffiert „No delivery date“ mit Summe, Anteil, Anzahl
    und den Business Units ohne jeden Termin.

  Kosten sind seit 24.10.2026 Erwartungswerte (in der Input Orchestration
  mit dem DeliveryScore gewichtet, Abschreibung 5 Jahre); Tooltip und
  Details zeigen zusätzlich die Kosten bei Lieferung (Kosten/Jahr ÷ Delivery).
  Die Aggregation steckt in `src/domain/value.ts` (wie die KPI-Kacheln im
  Browser, damit sie den Filtern folgt; kein eigener Backend-Endpunkt).
  Farben: Potenzial blau, Kosten orange (CSS-Variablen in `styles.css`).
- **Details** (Panel bzw. Dialog) — zusätzlich die vier Nutzen-Buckets,
  hypothetischer Nutzen, Confidence, Delivery, Potenzial, Kosten
  (einmalig, Betrieb, Abschreibung, Kosten/Jahr) und die Risikostufe.

**„Mehrwert“ = geschätztes Potenzial in €/Jahr** (`potential_value_eur` vom
Backend: Summe der Buckets × Confidence × Delivery). Alle Geldbeträge sind
Heuristik-Schätzungen und werden gerundet mit „≈“ angezeigt; die Risikostufe
trägt den Zusatz „estimated“.

Die Filter (Business Unit, Stage, Topic, Suche) gelten über alle
Ansichten hinweg. Alle Initiativen werden einmal vollständig geladen
(seitenweise, 500 pro Anfrage); Filtern, Sortieren und die KPI-Kacheln laufen
im Browser — damit reagieren auch die Kennzahlen auf die Filter, was
`/api/initiatives/summary` nicht kann. Bei deutlich mehr als einigen tausend
Initiativen wäre das neu zu überdenken.

## Lifecycle: Ideen, Freigabe, Formular 2

Nach den abgenommenen Entwürfen (F1 = bisheriges Formular mit Anpassungen,
User-Ansicht A, Approver-Ansicht A). Formular 2 ist **nicht mehr nach Gates
gegliedert**: Diese Zuordnung von Feldern zu Gates war nirgends dokumentiert und
ist entfernt. Modelliert ist stattdessen die Zuordnung **Stage ↔ Stage Gate** aus
der Form-2-Excel (Sheet1, Zeilen der Gate-Daten: „scope gate must be passed before
PoC, deploy gate must be passed before production“), `src/domain/lifecycle.ts`,
gleich wie im Backend (`app/lifecycle.py`, als `stage_gate_rules` in
`/api/form-options`):

| Stage | Scope-Gate | Deploy-Gate |
|---|---|---|
| Ideation | noch nicht passiert (geplant oder leer) | noch nicht passiert |
| PoC, MVP, Implementation | passiert (Datum bis heute) | noch nicht passiert |
| Production, Retired | passiert | passiert |
| On hold, Cancelled, Unknown | keine Regel | keine Regel |

Jedes Gate hat ein Datum (bis heute = passiert, später = geplant); gesetzte Daten
in Gate-Reihenfolge. Für Needs und Retire nennt die Excel keine Regel.

- **+ New AI idea** (`/new`) — Formular 1. **Alle Zahlen aus Wertebereichen**
  (Auswahllisten, `value_domains` aus `/api/form-options`, Fallback
  `VALUE_DOMAINS` in `src/domain/userInput.ts`; gespeichert wird der Wert der Spanne),
  laufende Kosten als Spanne, AI layer statt Solution Type. Je nach Stage fragt das
  Formular per Kalender nach den Daten der schon passierten Gates (PoC → Scope-Gate,
  Production → Scope und Deploy; Needs optional). **Stage startet mit Ideation**; eingereicht
  steht die Idee in Formular 2 damit zwischen Needs- und Scope-Gate. **Owner wählbar**: Standard
  „Me“ (der angemeldete Nutzer; ohne eigenen Owner-Eintrag fragt das Formular einmal die
  Business Unit), sonst jeder Eintrag aus `/api/owners` (`owner_id`, die Business Unit ist dann
  die des Owners); der Einreicher sieht die Idee weiter unter „My use cases“. Beim Efficiency-
  und Quality-Hebel heißen die Fälle **Runs** („Runs per year“, „Time saved per run“; Felder
  bleiben `cases_per_year`/`hours_saved_per_case`). Nach dem Absenden geht es zu „My use cases“.
- **My use cases** (`/my`) — alles, was ich eingereicht habe, besitze oder leite
  (Filter nach Rolle), Kennzahlen, „Needs your attention“ aus den To-dos des
  Backends (`revise_and_resubmit`, `complete_details`), Tabelle mit Freigabe,
  Stage, letztem passierten Gate (`last_gate`, Hinweis „check dates“, wenn Stage und
  Daten nicht passen), Potenzial (Vorschau mit `*`), Risiko und dem nächsten Schritt.
- **Use case** (`/use-cases/:id`) — **Stage und Stage Gates**: die Stages als
  Abfolge (Needs-Gate › Ideation › Scope-Gate › PoC … Retired),
  daneben „On hold“ und „Cancelled“; Stages unter der aus Formular 1
  (`stage_floor`) sind gesperrt. Darunter die vier Gate-Daten mit Status passed /
  planned / no date; ein passiertes Gate bleibt fest, außer die Stage verlangt es
  wieder in der Zukunft. Passen Stage und Daten nicht, zeigt das Gate die Meldung
  und Speichern ist gesperrt. **Die Idee** (Name, Beschreibung, Kostenschätzungen)
  ist nach dem Einreichen nur lesbar, außer beim Überarbeiten einer abgelehnten Idee.
  **Details (Formular 2)** jederzeit, auch vor der Freigabe. Gespeichert werden nur
  geänderte Felder, mit `base_revision` (409 → Meldung, neu laden).
- **Approvals** (`/approvals`, nur mit `canApprove` aus `/api/auth/rights`) —
  Inbox der wartenden Ideen; rechts Value-, Risk- und Effort-Check, Re-use-Check
  (`/similar`) und die Entscheidung: Lead zuweisen → freigeben (passiert das
  Needs-Gate heute, außer der Einreicher hat ein vergangenes Datum angegeben), oder
  mit Kommentar ablehnen.

**Noch nicht verarbeitet:** Alles, was in der UI gespeichert, aber noch nicht in
Silber/Gold verarbeitet ist, bleibt sichtbar und ist markiert (`processing` vom
Backend): „Estimate pending“ (neue Idee), „Changes pending“ (gespeicherte
Änderungen), „Not assessed“ (für Gold fehlen Eingaben). Solange etwas wartet,
lesen die Ansichten die Daten alle paar Sekunden neu.

## Abweichungen vom Entwurf — wegen der echten Daten

- **8 statt 4 Stage-Werte** (Ideation, PoC, MVP, Implementation,
  Production, On hold, Cancelled, Unknown; Idea und Exploration sind seit 11/2026
  zusammen Ideation). Das Board zeigt die fünf
  Pipeline-Spalten immer, On hold/Cancelled/Unknown nur wenn gefüllt.
- **Aufwand ist ein 1–10-Score** (5 Balken plus Zahl), **Mehrwert ein
  €-Betrag** (Zahl plus Balken). Das Potenzial reicht von ≈ 2,5k bis ≈ 460k €
  pro Jahr, darum nutzen Balken und Matrix-Y-Achse eine logarithmische Skala
  (1k bis 1 M €, außerhalb abgeschnitten).
- **Fehlende Werte werden benannt, nicht als 0 gezeigt** („not recorded",
  „not estimated", „no owner"). In der Matrix erscheinen nur Initiativen mit
  Aufwand und Potenzial (aktuell 68 von 165, der Aufwand fehlt in der Quelle
  oft); ein Hinweis nennt, wie viele fehlen. Identische Wertepaare werden auf
  einer kleinen Spirale gestreut, damit sie sichtbar bleiben.
- **KPI-Kacheln:** Initiativen, In progress, Potenzial/Jahr (mit Kosten/Jahr
  in der Notiz) und „Risk level 3+“ (ab Stufe 3 verlangt die
  Rahmenbetriebsvereinbarung die Beteiligung des Betriebsrats). Ein
  „Flagship-Initiative“-Kennzeichen gibt es in den Daten nicht.
- **Initiativen ohne Owner** haben keine Business Unit und bekommen im Filter
  den eigenen Eintrag „No business unit" (aktuell 23).
- **„+ Neue Initiative" und Benutzer-Avatar entfallen** — die API ist
  read-only; Anmeldung läuft über den Authenticator, angezeigt wird nur ein
  „Sign out"-Link.
- Der Katalog-Eintrag `-` bei Topic heißt „No topic"; ein unsichtbares
  Zeichen im Katalognamen „Connection lifecycle" wird beim Laden entfernt.
- Start/Lieferung stehen als „Q3 2026" mit dem Zusatz „(approx.)": die Quelle
  kennt nur Quartale, das Jahr ist eine Annahme (siehe Root-README).

## Authentifizierung

Nach dem Muster des Digital-Lab-Portals und des Plattform-Templates: OIDC über
den AAP-Authenticator mit dem internen Paket `eg-auth-react` (`ServiceApi`
hängt den Token als Bearer-Header an jeden API-Aufruf, `AuthManager` führt den
Login). Das Backend prüft den Token (`eg-auth`).

- `src/shared/api/serviceApi.ts` — `ServiceApi` mit `VITE_API` als Basis-URL;
  alle API-Aufrufe laufen darüber (nicht mehr über `fetch`).
- `src/shared/auth/` — `authManager.ts` (OIDC-Einstellungen), `AuthGate.tsx`
  (nur angemeldete Nutzer, sonst `/login`; wartet während der Prüfung statt zu
  früh umzuleiten), `LoginPage`, `LogoutPage`.
- `src/AuthApp.tsx` — Routing mit `/login`, `/logout` und der geschützten App.
- Fehlermeldungen: 401 (nicht angemeldet/Sitzung abgelaufen), 403, 503,
  Backend nicht erreichbar. Startet die Anmeldung nicht (z. B. weil
  `VITE_OIDC_*` fehlen), steht der Grund auf der Login-Seite.

**Konfiguration (Build-Zeit!):** `VITE_OIDC_CLIENT_ID`, `VITE_OIDC_AUTHORITY`,
`VITE_OIDC_REQUEST_GROUPS` in `.env.production` (bzw. `.env.development`).
Vite backt `VITE_*` beim Bauen ein — die Werte müssen den Build erreichen, nicht
den laufenden Pod. **Die Dateien enthalten bewusst leere Client-ID/Authority:**
Die Werte gehören ins Firmennetz (eigener OIDC-Client, Redirect-URI
`window.location.origin + "/"` exakt und je Stage registrieren). Authority und
Gruppe stehen im Template (`.env.production`); die Gruppe ist wie im Backend
ein Platzhalter.

**Lokal ohne Firmennetz (Dev-Bypass):** `.env.development.local`
(gitignored) mit `VITE_AUTH_DEV_BYPASS="true"` überspringt den Login; das
Backend muss mit `EG_AUTH_DEV_MODE=True` laufen. Der Bypass gilt nur im
Dev-Server (`import.meta.env.DEV`) — ein Produktions-Build ignoriert ihn, auch
wenn die Variable in der Build-Umgebung steht (getestet).

**Demo-Rolle (auch in Produktion):** Konten aus `AI_COCKPIT_DEMO_PRESENTERS`
(Backend) sehen oben den Schalter **Normal user / Approver (demo)**. Sie
arbeiten als normaler Nutzer und wechseln für eine Demo in den Approver-Modus:
das Frontend sendet dann `X-Demo-Role: approver` (je Browser-Tab gemerkt), das
Backend wertet den Header nur für diese Konten aus. Allen anderen wird der
Schalter nicht angezeigt.

## Lokal starten

```bash
cd frontend
# eg-auth-react ist ein internes Paket und nicht auf dem öffentlichen npm.
# Lokal: Kopie nach local_packages/eg-auth-react/ legen (dist/ + package.json,
# z. B. aus dem Digital-Lab-Portal) und dann EINMAL so installieren:
npm install --no-save --registry=https://registry.npmjs.org/ ./local_packages/eg-auth-react
npm run dev            # http://localhost:5173, proxied /api -> http://localhost:8000
# Tests: dieser Branch führt die Test-Abhängigkeiten (@testing-library/*, jsdom)
# nicht in package.json; lokal einmal ohne Speichern nachinstallieren:
#   npm install --no-save --registry=https://registry.npmjs.org/ @testing-library/react @testing-library/user-event jsdom
npx vitest run         # Vitest
npm run lint           # tsc (der Build prüft keine Typen, wie im Template)
npm run build          # build/  (vite build --mode production, wie im Template)
```

`.npmrc` zeigt auf den Firmen-Spiegel — so erwartet es die Plattform. Dort ist
er von außen nicht erreichbar, deshalb der Registry-Override im Befehl oben
(nur lokal). `.node-version` (22) und `engines` entsprechen dem Template.

`package.json` führt `eg-auth-react` mit `3.0.0` — das ist der Stand für das
Firmennetz, dort löst der Spiegel es auf. Ein reines `npm install` schlägt
deshalb lokal fehl; der Befehl oben installiert alles andere mit.
`local_packages/` ist gitignored und darf nie ins Repository (internes Paket).
Ebenso gitignored: `package-lock.json` — sie muss im Firmennetz erzeugt werden
(interne Registry); eine hier erzeugte zeigt aufs öffentliche npm und führt dort
zu Timeouts. Beim Einchecken der Firmen-Lockfile die Zeile in `.gitignore`
entfernen.

Das Backend muss laufen und mit Dev-Modus gestartet sein (siehe
`backend/README.md`). Anderes Proxy-Ziel: `VITE_DEV_API_TARGET`. Wie `/api` im
Cluster zum Backend geroutet wird (Route auf gleicher Domain), ist eine
Deployment-Entscheidung und noch offen; ein direkter Aufruf eines anderen
Hosts bräuchte CORS-Freigaben im Backend, die es nicht hat.

## Verifiziert

56 Tests (Filter, Flagship-Statistik und -Widget, Sortierung mit fehlenden Werten, KPI-Berechnung,
€-Formatierung und Log-Skala, Matrix-Layout, Value-Aggregation (Brücke, Break-even, Fahrplan) und -Ansicht, Anzeige-Bereinigung, Ansichten, Detaildialog, Fehlerzustände je
HTTP-Status, Anmeldeschranke in allen Zuständen, Login-Seite, Dev-Bypass
inkl. Produktions-Absicherung). Getestet gegen eine **Attrappe** von
`ServiceApi`/`useAuth`, nicht gegen echtes OIDC.

Im Browser geprüft (23.10.2026): (1) Dev-Bypass gegen das Backend im Dev-Modus
und die echte DB — Liste und Board zeigen alle 165 Initiativen, die Matrix 68
mit Hinweis auf 97 ohne Aufwand, Detailpanel mit Buckets/Kosten/Risikostufe; (2) ohne Bypass führt jede geschützte URL zu
`/login`, es gehen keine API-Aufrufe raus; (3) Produktions-Build mit gesetzter
Bypass-Variable enthält die Anmeldeschranke und keinen Bypass. Auf einem
frischen Klon (ohne `node_modules`/Lockfile) genügt der Install-Befehl oben für
Typecheck, Tests und Build; die Schriften kommen vom eigenen Server (6 Dateien,
keine externen Anfragen).

**Nicht geprüft:** ein echter Login gegen den Authenticator (hier nicht
erreichbar, OIDC-Client noch nicht registriert), das Zusammenspiel des Tokens
mit dem echten `eg-auth` im Backend, Token-Erneuerung bei langen Sitzungen.

Nicht gemacht: Cluster-Routing; mobile Feinabstimmung über die Grundlayouts
hinaus. Unbelegt ist, welches Verzeichnis das S2I-Image ausliefert — wir
folgen dem Template (`build/`), geprüft werden kann das erst beim ersten Build
im Firmennetz.
