# Frontend — React Dashboard

Eigenes Kubernetes-Deployment, eigene Anwendung. Konsumiert ausschließlich die
read-only Backend-API (`/api/initiatives`); kein eigener Datenzugriff.
React 18 + Vite + TypeScript (Versionen wie das Plattform-Template, damit sie
der Firmen-Spiegel führt; mit diesen Versionen getestet), Schrift (IBM Plex)
als Dateien im Repo (`src/fonts/`, OFL-Lizenzen liegen bei; bewusst keine
npm-Pakete, die der Firmen-Spiegel eventuell nicht führt), keine externen
Requests zur Laufzeit.

## Ansichten (nach den abgenommenen Entwürfen)

- **Matrix** (`/`) — Aufwand × Mehrwert als Quadranten-Plot, KPI-Kacheln,
  Detailpanel zur angeklickten Initiative.
- **Liste** (`/liste`) — sortierbare Tabelle, Filter links (Status,
  Business Unit, Flagship), Klick auf den Namen öffnet die Details.
- **Board** (`/board`) — Spalten je Status, Karten mit Owner, Aufwand,
  Mehrwert; Klick öffnet die Details.

Die Filter (Business Unit, Status, Flagship, Suche) gelten über alle
Ansichten hinweg. Alle Initiativen werden einmal vollständig geladen
(seitenweise, 500 pro Anfrage); Filtern, Sortieren und die KPI-Kacheln laufen
im Browser — damit reagieren auch die Kennzahlen auf die Filter, was
`/api/initiatives/summary` nicht kann. Bei deutlich mehr als einigen tausend
Initiativen wäre das neu zu überdenken.

## Abweichungen vom Entwurf — wegen der echten Daten

- **9 statt 4 Status-Werte** (Idea, Exploration, PoC, MVP, Implementation,
  Production, On hold, Cancelled, Unknown). Das Board zeigt die sechs
  Pipeline-Spalten immer, On hold/Cancelled/Unknown nur wenn gefüllt.
- **Aufwand und Mehrwert sind 1–10-Scores**, keine T-Shirt-Größen: Aufwand
  als 5 Balken plus Zahl, Mehrwert als Zahl plus Balken.
- **Fehlende Werte werden benannt, nicht als 0 gezeigt** („nicht erfasst",
  „kein Owner"). In der Matrix erscheinen nur Initiativen mit beiden Scores
  (aktuell 65 von 160); ein Hinweis nennt, wie viele fehlen. Identische
  Score-Paare werden auf einer kleinen Spirale gestreut, damit sie sichtbar
  bleiben.
- **KPI-Kachel „Flagship-Initiativen" ersetzt durch „Ohne Mehrwert"** — ein
  „Flagship-Initiative"-Kennzeichen gibt es in den Daten nicht, die Lücke beim
  Mehrwert (94 von 160) ist dagegen die wichtigste Datenaussage.
- **Initiativen ohne Owner** haben keine Business Unit und bekommen im Filter
  den eigenen Eintrag „Ohne Business Unit" (aktuell 22).
- **„+ Neue Initiative" und Benutzer-Avatar entfallen** — die API ist
  read-only; Anmeldung läuft über den Authenticator, angezeigt wird nur ein
  „Abmelden"-Link.
- Der Katalog-Eintrag `-` bei Flagship heißt „Kein Flagship"; ein unsichtbares
  Zeichen im Katalognamen „Connection lifecycle" wird beim Laden entfernt.
- Start/Lieferung stehen als „Q3 2026" mit dem Zusatz „(grob)": die Quelle
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

## Lokal starten

```bash
cd frontend
# eg-auth-react ist ein internes Paket und nicht auf dem öffentlichen npm.
# Lokal: Kopie nach local_packages/eg-auth-react/ legen (dist/ + package.json,
# z. B. aus dem Digital-Lab-Portal) und dann EINMAL so installieren:
npm install --no-save --registry=https://registry.npmjs.org/ ./local_packages/eg-auth-react
npm run dev            # http://localhost:5173, proxied /api -> http://localhost:8000
npm test               # Vitest
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

30 Tests (Filter, Sortierung mit fehlenden Werten, KPI-Berechnung, Matrix-
Layout, Anzeige-Bereinigung, Ansichten, Detaildialog, Fehlerzustände je
HTTP-Status, Anmeldeschranke in allen Zuständen, Login-Seite, Dev-Bypass
inkl. Produktions-Absicherung). Getestet gegen eine **Attrappe** von
`ServiceApi`/`useAuth`, nicht gegen echtes OIDC.

Im Browser geprüft: (1) Dev-Bypass gegen das Backend im Dev-Modus — alle 160
Initiativen, keine Konsolenfehler; (2) ohne Bypass führt jede geschützte URL zu
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
