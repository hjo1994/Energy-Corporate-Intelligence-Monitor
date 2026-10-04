import { NavLink, Route, Routes } from "react-router-dom";
import { AUTH_DEV_BYPASS } from "./shared/auth/devBypass";
import { AppProvider, useApp } from "./store";
import { BoardView } from "./views/BoardView";
import { ListView } from "./views/ListView";
import { MatrixView } from "./views/MatrixView";

function Shell() {
  const { load, reload, filters, setFilters } = useApp();
  return (
    <div className="page">
      <header className="topbar">
        <div className="brand">
          <span className="logo" aria-hidden="true" />
          <span className="brand-name">AI Cockpit</span>
        </div>
        <nav className="tabs" aria-label="Ansichten">
          <NavLink to="/" end>
            Matrix
          </NavLink>
          <NavLink to="/liste">Liste</NavLink>
          <NavLink to="/board">Board</NavLink>
        </nav>
        {!AUTH_DEV_BYPASS && (
          <NavLink to="/logout" className="logout">
            Abmelden
          </NavLink>
        )}
        <label className="search">
          <span className="sr-only">Initiative suchen</span>
          <input
            type="search"
            placeholder="Initiative suchen…"
            value={filters.search}
            onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))}
          />
        </label>
      </header>

      <main>
        {load.state === "loading" && <p className="state" role="status">Daten werden geladen …</p>}
        {load.state === "error" && (
          <div className="state card" role="alert">
            <p>{load.message}</p>
            <button type="button" className="primary" onClick={reload}>
              Erneut versuchen
            </button>
          </div>
        )}
        {load.state === "ready" && (
          <Routes>
            <Route path="/" element={<MatrixView />} />
            <Route path="/liste" element={<ListView />} />
            <Route path="/board" element={<BoardView />} />
            <Route path="*" element={<MatrixView />} />
          </Routes>
        )}
      </main>
    </div>
  );
}

export default function App() {
  return (
    <AppProvider>
      <Shell />
    </AppProvider>
  );
}
