import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { hasAuthParams, useAuth } from "eg-auth-react";

import { AUTH_DEV_BYPASS } from "./devBypass";

function Centered({ children }: { children: ReactNode }) {
  return <div className="state">{children}</div>;
}

/** Lets only signed-in users through; sends everyone else to /login. */
export function OidcGate({ children }: { children: ReactNode }) {
  const auth = useAuth();

  if (hasAuthParams() || auth.activeNavigator === "signinSilent" || auth.isLoading) {
    return (
      <Centered>
        <p role="status">Checking sign-in …</p>
      </Centered>
    );
  }

  if (auth.error) {
    return (
      <Centered>
        <div className="card state" role="alert">
          <p>
            Sign-in error: {auth.error.message}
          </p>

          <a className="primary-link" href="/login">
            Go to sign-in
          </a>
        </div>
      </Centered>
    );
  }

  if (!auth.isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}

const PassThrough = ({ children }: { children: ReactNode }) => <>{children}</>;

/** The gate in use: none with the local dev bypass, the OIDC gate otherwise. */
export const AuthGate = AUTH_DEV_BYPASS ? PassThrough : OidcGate;