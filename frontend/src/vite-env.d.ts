/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API: string;
  readonly VITE_OIDC_CLIENT_ID: string;
  readonly VITE_OIDC_AUTHORITY: string;
  readonly VITE_OIDC_REQUEST_GROUPS: string;
  readonly VITE_AUTH_DEV_BYPASS?: string;
  /** "true": the role switch offers only the roles the rights allow (off by default, see nav/roles.ts) */
  readonly VITE_ROLE_GATING?: string;
}
