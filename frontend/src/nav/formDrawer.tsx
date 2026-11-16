import { createContext, useContext, useEffect } from "react";
import { Navigate } from "react-router-dom";

/** Form 1 opens in a drawer over the innovator pages; `enabled` follows the backend's feature switch. */
export interface FormDrawer {
  enabled: boolean;
  open: () => void;
}

export const FormDrawerCtx = createContext<FormDrawer>({ enabled: false, open: () => undefined });

export const useFormDrawer = (): FormDrawer => useContext(FormDrawerCtx);

/** The former /new page: the start page with form 1 open over it. */
export function OpenFormRoute() {
  const { open } = useFormDrawer();
  useEffect(() => open(), [open]);
  return <Navigate to="/innovate/start" replace />;
}
