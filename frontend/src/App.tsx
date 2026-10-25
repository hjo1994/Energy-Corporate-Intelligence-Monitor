import { Navigate, NavLink, Route, Routes } from "react-router-dom";
import { AUTH_DEV_BYPASS } from "./shared/auth/devBypass";
import { AppProvider, useApp } from "./store";
import { BoardView } from "./views/BoardView";
import { ListView } from "./views/ListView";
import { CockpitView } from "./views/CockpitView";

function Shell() {
  const { load, reload, filters, setFilters } = useApp();
  return (
    <div className="page">
      <header className="topbar">
        <div className="brand">
          <span className="logo" aria-hidden="true" />
          <span className="brand-name">AI Cockpit</span>
        </div>
        <nav className="tabs" aria-label="Views">
          <NavLink to="/" end>
            Cockpit
          </NavLink>
          <NavLink to="/list">List</NavLink>
          <NavLink to="/board">Board</NavLink>
        </nav>
        {!AUTH_DEV_BYPASS && (
          <NavLink to="/logout" className="logout">
            Sign out
          </NavLink>
        )}
        <label className="search">
          <span className="sr-only">Search initiatives</span>
          <input
            type="search"
            placeholder="Search initiatives…"
            value={filters.search}
            onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))}
          />
        </label>
      </header>

      <main>
        {load.state === "loading" && <p className="state" role="status">Loading data …</p>}
        {load.state === "error" && (
          <div className="state card" role="alert">
            <p>{load.message}</p>
            <button type="button" className="primary" onClick={reload}>
              Try again
            </button>
          </div>
        )}
        {load.state === "ready" && (
          <Routes>
            <Route path="/" element={<CockpitView />} />
            <Route path="/list" element={<ListView />} />
            <Route path="/board" element={<BoardView />} />
            {/* the former Value tab now lives on the start page */}
            <Route path="/value" element={<Navigate to="/" replace />} />
            <Route path="*" element={<CockpitView />} />
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
