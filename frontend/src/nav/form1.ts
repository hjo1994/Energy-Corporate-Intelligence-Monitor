import { createContext, useContext } from "react";

/** Form 1 is its own page in the Innovator view (/innovate/new); `enabled` follows the backend's feature switch. */
export interface Form1 {
  enabled: boolean;
  open: () => void;
}

export const FORM1_PATH = "/innovate/new";

export const Form1Ctx = createContext<Form1>({ enabled: false, open: () => undefined });

export const useForm1 = (): Form1 => useContext(Form1Ctx);
