import "./fonts/fonts.css";
import "./styles.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App";
import { AUTH_DEV_BYPASS } from "./shared/auth/devBypass";

const root = createRoot(document.getElementById("root")!);

if (AUTH_DEV_BYPASS) {
  root.render(
    <StrictMode>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </StrictMode>,
  );
} else {
  // Loaded on demand so that nothing of the OIDC setup runs with the dev bypass.
  const { default: AuthApp } = await import("./AuthApp");
  root.render(
    <StrictMode>
      <AuthApp />
    </StrictMode>,
  );
}
