import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { fetchAllInitiatives } from "./api/client";
import type { Initiative } from "./api/types";
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
}

const Ctx = createContext<AppState | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [load, setLoad] = useState<Load>({ state: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [filters, setFiltersState] = useState<Filters>(EMPTY_FILTERS);

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
  const setFilters = useCallback((update: (f: Filters) => Filters) => setFiltersState(update), []);

  const all = useMemo(() => (load.state === "ready" ? load.items : []), [load]);
  const visible = useMemo(() => applyFilters(all, filters), [all, filters]);

  const value = useMemo(
    () => ({ load, reload, filters, setFilters, all, visible }),
    [load, reload, filters, setFilters, all, visible],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useApp must be used inside <AppProvider>");
  return v;
}
