import { useState } from "react";

import { authManager } from "./authManager";

const nonce = () => Math.random().toString(36).substring(2, 15);

export function LoginPage() {
  const [error, setError] = useState<string | null>(null);

  const login = () => {
    setError(null);

    // Typical cause: VITE_OIDC_AUTHORITY / VITE_OIDC_CLIENT_ID were not set for this build.
    authManager.userManager
      .signinRedirect({ nonce: nonce() })
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : "Unknown error");
      });
  };

  return (
    <div className="login">
      <div className="card login-card">
        <span className="logo" aria-hidden="true" />

        <h1>AI Cockpit</h1>

        <p className="muted">
          Overview of all AI initiatives. Please sign in.
        </p>

        <button
          type="button"
          className="primary"
          onClick={login}
        >
          Sign in
        </button>

        {error && (
          <p role="alert" className="missing">
            Sign-in could not be started: {error}. Is the OIDC configuration
            (VITE_OIDC_*) set for this build?
          </p>
        )}
      </div>
    </div>
  );
}