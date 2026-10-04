import { ServiceApi } from "eg-auth-react";

// ServiceApi (axios) sends the OIDC access token as a Bearer header once a user is signed in.
export const serviceApi = new ServiceApi({ baseURL: import.meta.env.VITE_API });
