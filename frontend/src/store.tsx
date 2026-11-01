import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { fetchAllInitiatives, fetchRights } from "./api/client";
import type { Initiative, Rights } from "./api/types";
import { applyFilters, EMPTY_FILTERS, type Filters } from "./domain/filters";

type Load =
  | { state: "loading" }
  | { state: "error"; message: string }
  | { state: "ready"; items: Initiative[] };

interface AppState {
  load: Load;
  reload: () => void;
  filters: Filters;
  setFilters: (update: (f: Filters) => Filters) => void;
  /** all initiatives, unfiltered — for building filter options with stable counts */
  all: Initiative[];
  /** initiatives matching the current filters */
  visible: Initiative[];
  /** show an initiative just created through the input form right away (it is "pending") */
  addInitiative: (initiative: Initiative) => void;
  /** what the signed-in user may do (approver inbox, admin) */
  rights: Rights;
  /** re-read the rights, e.g. after the first use case made the user an owner */
  reloadRights: () => void;
}

// While initiatives entered through the form are pending, the list is re-read this often until
// the pipeline has turned them into regular initiatives.
export const PENDING_POLL_MS = 3000;

const Ctx = createContext<AppState | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [load, setLoad] = useState<Load>({ state: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [filters, setFiltersState] = useState<Filters>(EMPTY_FILTERS);
  const [rights, setRights] = useState<Rights>({ canApprove: false, canAdmin: false });

  const [rightsAttempt, setRightsAttempt] = useState(0);
  useEffect(() => {
    let cancelled = false;
    fetchRights().then((r) => !cancelled && setRights(r));
    return () => {
      cancelled = true;
    };
  }, [rightsAttempt]);
  const reloadRights = useCallback(() => setRightsAttempt((n) => n + 1), []);

  useEffect(() => {
    let cancelled = false;
    setLoad({ state: "loading" });
    fetchAllInitiatives().then(
      (items) => !cancelled && setLoad({ state: "ready", items }),
      (err: unknown) => {
        if (cancelled) return;
        setLoad({
          state: "error",
          message: err instanceof Error ? err.message : "The data could not be loaded.",
        });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);
  const addInitiative = useCallback(
    (initiative: Initiative) =>
      setLoad((l) => (l.state === "ready" ? { state: "ready", items: [...l.items, initiative] } : l)),
    [],
  );

  // re-read while the pipeline still has to process something the users entered
  const hasPending =
    load.state === "ready" && load.items.some((i) => i.status === "pending" || i.processing === "changes_pending");
  useEffect(() => {
    if (!hasPending) return;
    let cancelled = false;
    const timer = setInterval(() => {
      // silent refresh: keep showing the current data, ignore a failed attempt
      fetchAllInitiatives().then(
        (items) => !cancelled && setLoad({ state: "ready", items }),
        () => undefined,
      );
    }, PENDING_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [hasPending]);
  const setFilters = useCallback((update: (f: Filters) => Filters) => setFiltersState(update), []);

  const all = useMemo(() => (load.state === "ready" ? load.items : []), [load]);
  const visible = useMemo(() => applyFilters(all, filters), [all, filters]);

  const value = useMemo(
    () => ({ load, reload, filters, setFilters, all, visible, addInitiative, rights, reloadRights }),
    [load, reload, filters, setFilters, all, visible, addInitiative, rights, reloadRights],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useApp must be used inside <AppProvider>");
  return v;
}
