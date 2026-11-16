import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { Navigate, NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { fetchApprovals, fetchFeatures, fetchMyUseCases } from "./api/client";
import { AUTH_DEV_BYPASS } from "./shared/auth/devBypass";
import { DemoRoleSwitch } from "./components/DemoRoleSwitch";
import { FORM1_PATH, Form1Ctx } from "./nav/form1";
import { allowedRoles, roleGating, roleHome, roleOfPath, ROLES, storedRole, storeRole, type Role } from "./nav/roles";
import { AppProvider, useApp } from "./store";
import { BoardView } from "./views/BoardView";
import { ListView } from "./views/ListView";
import { CockpitView } from "./views/CockpitView";
import { NewInitiativeView } from "./views/NewInitiativeView";
import { ApprovalsView } from "./views/ApprovalsView";
import { UsersView } from "./views/UsersView";
import { MyUseCasesView } from "./views/MyUseCasesView";
import { UseCaseView } from "./views/UseCaseView";
import { StartView } from "./views/StartView";
import { ExploreView } from "./views/ExploreView";

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

/** Innovator | Approver | Management; hidden for users with one role only. */
function RoleSwitch({ roles, current, approvals, onChoose }: { roles: Role[]; current: Role; approvals: number; onChoose: (r: Role) => void }) {
  if (roles.length < 2) return null;
  return (
    <div className="role-switch" role="group" aria-label="Role">
      {ROLES.filter((r) => roles.includes(r.id)).map((r) => (
        <button
          key={r.id}
          type="button"
          aria-pressed={r.id === current}
          className={r.id === current ? "role-opt role-current" : "role-opt"}
          onClick={() => onChoose(r.id)}
        >
          {r.label}
          {r.id === "approve" && r.id !== current && <Count n={approvals} label="waiting" />}
        </button>
      ))}
    </div>
  );
}

/** Approver overview: the list and the board (the value dashboard is Management's only). */
function Overview() {
  return (
    <>
      <nav className="subtabs" aria-label="Overview">
        <NavLink to="/approve/overview/list">List</NavLink>
        <NavLink to="/approve/overview/board">Board</NavLink>
      </nav>
      <Routes>
        <Route index element={<Navigate to="/approve/overview/list" replace />} />
        <Route path="list" element={<ListView />} />
        <Route path="board" element={<BoardView />} />
        <Route path="*" element={<Navigate to="/approve/overview/list" replace />} />
      </Routes>
    </>
  );
}

/** A role's pages: only for users with that role (sent to their own start otherwise). */
function RolePage({ role, roles, children }: { role: Role; roles: Role[]; children: ReactNode }) {
  const { rightsReady } = useApp();
  if (!rightsReady) return <p className="state" role="status">Loading …</p>;
  return roles.includes(role) ? <>{children}</> : <Navigate to={roleHome(roles[0])} replace />;
}

function Home({ role, roles }: { role: Role; roles: Role[] }) {
  const { rightsReady } = useApp();
  if (!rightsReady) return <p className="state" role="status">Loading …</p>;
  return <Navigate to={roleHome(roles.includes(role) ? role : roles[0])} replace />;
}

function Shell() {
  const { load, reload, filters, setFilters, rights } = useApp();
  const location = useLocation();
  const navigate = useNavigate();
  const counts = useCounts(rights.canApprove);
  const roles = useMemo(() => allowedRoles(rights, AUTH_DEV_BYPASS), [rights]);

  // the role in the URL wins; elsewhere (a use case page, the start) the last one chosen counts
  const pathRole = roleOfPath(location.pathname);
  const [lastRole, setLastRole] = useState<Role>(() => storedRole() ?? "innovate");
  useEffect(() => {
    if (pathRole && pathRole !== lastRole) {
      setLastRole(pathRole);
      storeRole(pathRole);
    }
  }, [pathRole, lastRole]);
  const role = pathRole ?? lastRole;

  // AI_COCKPIT_ENABLE_INITIATIVE_INPUT on the backend; hidden until it says yes
  // null until the backend has answered
  const [features, setFeatures] = useState<boolean | null>(null);
  const inputEnabled = features === true;
  useEffect(() => {
    let cancelled = false;
    fetchFeatures().then((f) => !cancelled && setFeatures(f.initiative_input));
    return () => {
      cancelled = true;
    };
  }, []);
  const openForm = useCallback(() => navigate(FORM1_PATH), [navigate]);
  const form1 = useMemo(() => ({ enabled: inputEnabled, open: openForm }), [inputEnabled, openForm]);

  const tabs: { to: string; label: string; count?: ReactNode }[] =
    role === "innovate"
      ? [
          { to: "/innovate/start", label: "Start" },
          { to: "/innovate/explore", label: "Exploration" },
          { to: "/innovate/my", label: "My use cases", count: <Count n={counts.todos} label="to-dos" /> },
        ]
      : role === "approve"
        ? [
            { to: "/approve/overview", label: "Use cases" },
            { to: "/approve/approvals", label: "Approvals", count: <Count n={counts.approvals} label="waiting" /> },
          ]
        : [
            { to: "/steer/value", label: "Value dashboard" },
            ...(rights.canManageUsers ? [{ to: "/steer/users", label: "Users" }] : []),
          ];

  const inRole = (r: Role, page: ReactNode) => (
    <RolePage role={r} roles={roles}>
      {page}
    </RolePage>
  );

  return (
    <Form1Ctx.Provider value={form1}>
      <div className="page">
        <header className="topbar">
          <div className="brand">
            <span className="logo" aria-hidden="true" />
            <span className="brand-name">AI Cockpit</span>
          </div>
          <RoleSwitch roles={roles} current={role} approvals={counts.approvals} onChoose={(r) => r !== role && navigate(roleHome(r))} />
          <nav className="tabs" aria-label="Views">
            {tabs.map((t) => (
              <NavLink key={t.to} to={t.to}>
                {t.label} {t.count}
              </NavLink>
            ))}
          </nav>
          {inputEnabled && role === "innovate" && (
            <button type="button" className="new-btn" onClick={openForm}>
              + New AI idea
            </button>
          )}
          {roleGating() && <DemoRoleSwitch />}
          {!AUTH_DEV_BYPASS && (
            <NavLink to="/logout" className="logout">
              Sign out
            </NavLink>
          )}
          {role !== "innovate" && (
            <label className="search">
              <span className="sr-only">Search initiatives</span>
              <input
                type="search"
                placeholder="Search initiatives…"
                value={filters.search}
                onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))}
              />
            </label>
          )}
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
              <Route path="/" element={<Home role={lastRole} roles={roles} />} />
              <Route path="/innovate" element={<Navigate to="/innovate/start" replace />} />
              <Route path="/innovate/start" element={<StartView />} />
              <Route path="/innovate/explore" element={<ExploreView />} />
              <Route path="/innovate/my" element={<MyUseCasesView />} />
              <Route
                path={FORM1_PATH}
                element={
                  features === null ? (
                    <p className="state" role="status">Loading …</p>
                  ) : inputEnabled ? (
                    <NewInitiativeView />
                  ) : (
                    <Navigate to="/innovate/start" replace />
                  )
                }
              />
              <Route path="/approve" element={<Navigate to="/approve/overview/list" replace />} />
              <Route path="/approve/overview/*" element={inRole("approve", <Overview />)} />
              <Route path="/approve/approvals" element={inRole("approve", <ApprovalsView />)} />
              <Route path="/steer" element={<Navigate to="/steer/value" replace />} />
              <Route path="/steer/value" element={inRole("steer", <CockpitView />)} />
              <Route path="/steer/users" element={inRole("steer", <UsersView />)} />
              <Route path="/use-cases/:id" element={<UseCaseView />} />
              {/* the routes before the role navigation (11/2026) */}
              <Route path="/list" element={<Navigate to="/approve/overview/list" replace />} />
              <Route path="/board" element={<Navigate to="/approve/overview/board" replace />} />
              <Route path="/my" element={<Navigate to="/innovate/my" replace />} />
              <Route path="/approvals" element={<Navigate to="/approve/approvals" replace />} />
              <Route path="/users" element={<Navigate to="/steer/users" replace />} />
              <Route path="/value" element={<Navigate to="/steer/value" replace />} />
              <Route path="/new" element={<Navigate to={FORM1_PATH} replace />} />
              <Route path="*" element={<Home role={lastRole} roles={roles} />} />
            </Routes>
          )}
        </main>
      </div>
    </Form1Ctx.Provider>
  );
}

export default function App() {
  return (
    <AppProvider>
      <Shell />
    </AppProvider>
  );
}
