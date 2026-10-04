import { useState } from "react";

import { authManager } from "./authManager";

const nonce = () => Math.random().toString(36).substring(2, 15);

export function LoginPage() {
  const [error, setError] = useState<string | null>(null);

  const login = () => {
    setError(null);
    // Typical cause: VITE_OIDC_AUTHORITY / VITE_OIDC_CLIENT_ID were not set for this build.
    authManager.userManager.signinRedirect({ nonce: nonce() }).catch((e: unknown) => {
      setError(e instanceof Error ? e.message : "Unbekannter Fehler");
    });
  };

  return (
    <div className="login">
      <div className="card login-card">
        <span className="logo" aria-hidden="true" />
        <h1>AI Cockpit</h1>
        <p className="muted">Übersicht über alle KI-Initiativen. Bitte melden Sie sich an.</p>
        <button type="button" className="primary" onClick={login}>
          Anmelden
        </button>
        {error && (
          <p role="alert" className="missing">
            Die Anmeldung konnte nicht gestartet werden: {error}. Ist die OIDC-Konfiguration (VITE_OIDC_*) für diesen Build gesetzt?
          </p>
        )}
      </div>
    </div>
  );
}
