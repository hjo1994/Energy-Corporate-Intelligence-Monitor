import { useEffect, useState } from "react";
import { Navigate, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { fetchApprovals, fetchFeatures, fetchMyUseCases } from "./api/client";
import { AUTH_DEV_BYPASS } from "./shared/auth/devBypass";
import { DevUserSwitch } from "./shared/auth/DevUserSwitch";
import { ViewAsSwitch } from "./components/ViewAsSwitch";
import { AppProvider, useApp } from "./store";
import { BoardView } from "./views/BoardView";
import { ListView } from "./views/ListView";
import { CockpitView } from "./views/CockpitView";
import { NewInitiativeView } from "./views/NewInitiativeView";
import { ApprovalsView } from "./views/ApprovalsView";
import { MyUseCasesView } from "./views/MyUseCasesView";
import { UseCaseView } from "./views/UseCaseView";

/** Badge counts in the tabs: my open to-dos and the ideas waiting for a decision. */
function useCounts(canApprove: boolean): { todos: number; approvals: number } {
  const location = useLocation();
  const [counts, setCounts] = useState({ todos: 0, approvals: 0 });
  useEffect(() => {
    let cancelled = false;
    fetchMyUseCases().then(
      (mine) => !cancelled && setCounts((c) => ({ ...c, todos: Array.isArray(mine) ? mine.filter((u) => u.todos?.length > 0).length : 0 })),
      () => undefined,
    );
    if (canApprove) {
      fetchApprovals().then(
        (items) => !cancelled && setCounts((c) => ({ ...c, approvals: Array.isArray(items) ? items.length : 0 })),
        () => undefined,
      );
    }
    return () => {
      cancelled = true;
    };
  }, [canApprove, location.pathname]);
  return counts;
}

const Count = ({ n, label }: { n: number; label: string }) =>
  n > 0 ? <span className="tab-count" aria-label={`${n} ${label}`}>{n}</span> : null;

function Shell() {
  const { load, reload, filters, setFilters, rights, viewAsSubmitter } = useApp();
  const counts = useCounts(rights.canApprove);
  // AI_COCKPIT_ENABLE_INITIATIVE_INPUT on the backend; hidden until it says yes
  const [inputEnabled, setInputEnabled] = useState(false);
  useEffect(() => {
    let cancelled = false;
    fetchFeatures().then((f) => !cancelled && setInputEnabled(f.initiative_input));
    return () => {
      cancelled = true;
    };
  }, []);
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
          <NavLink to="/my">
            My use cases <Count n={counts.todos} label="to-dos" />
          </NavLink>
          {rights.canApprove && (
            <NavLink to="/approvals">
              Approvals <Count n={counts.approvals} label="waiting" />
            </NavLink>
          )}
        </nav>
        {inputEnabled && (
          <NavLink to="/new" className="new-btn">
            + New AI idea
          </NavLink>
        )}
        <ViewAsSwitch />
        {AUTH_DEV_BYPASS ? (
          <DevUserSwitch />
        ) : (
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
            <Route path="/new" element={inputEnabled ? <NewInitiativeView /> : <Navigate to="/" replace />} />
            <Route path="/my" element={<MyUseCasesView />} />
            <Route path="/use-cases/:id" element={<UseCaseView />} />
            <Route path="/approvals" element={viewAsSubmitter ? <Navigate to="/my" replace /> : <ApprovalsView />} />
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
