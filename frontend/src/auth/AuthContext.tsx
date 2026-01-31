import {createContext, ReactNode, useContext, useEffect, useMemo, useRef, useState} from "react";
import keycloak from "./keycloak";

type AuthState = {
  initialized: boolean;
  authenticated: boolean;
  token?: string;
  username?: string;
  login: () => void;
  logout: () => void;
  getToken: () => Promise<string | undefined>;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({children}: { children: ReactNode }) {
  const [initialized, setInitialized] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [token, setToken] = useState<string | undefined>(undefined);
  const [username, setUsername] = useState<string | undefined>(undefined);
  const didInit = useRef(false);

  useEffect(() => {
    if (didInit.current) return;         // prevents double init in React StrictMode (dev)
    didInit.current = true;

    let intervalId: number | undefined;

    (async () => {
      try {
        const ok = await keycloak.init({
          onLoad: "check-sso",
          pkceMethod: "S256",
          checkLoginIframe: false,

          // IMPORTANT:
          // comment this OUT unless you created /public/silent-check-sso.html
          // silentCheckSsoRedirectUri: window.location.origin + "/silent-check-sso.html",
        });

        console.log("KC authenticated:", keycloak.authenticated);
        console.log("KC token endpoint base:", keycloak.authServerUrl);
        console.log("URL after redirect:", window.location.href);

        setAuthenticated(!!keycloak.authenticated);
        setToken(keycloak.token ?? undefined);
        setUsername(keycloak.tokenParsed?.preferred_username as string | undefined);

        // Token refresh loop (only start once init succeeded)
        intervalId = window.setInterval(async () => {
          if (!keycloak.authenticated) return;
          try {
            const refreshed = await keycloak.updateToken(30);
            if (refreshed) {
              setToken(keycloak.token);
              setUsername(keycloak.tokenParsed?.preferred_username as string | undefined);
            }
          } catch {
            // noop for dev
          }
        }, 10_000);

      } catch (e) {
        console.error("Keycloak init failed:", e);
        setAuthenticated(false);
        setToken(undefined);
        setUsername(undefined);
      } finally {
        // This is the key: never get stuck on "Init…"
        setInitialized(true);
      }
    })();

    return () => {
      if (intervalId) window.clearInterval(intervalId);
    };
  }, []);


  const value = useMemo<AuthState>(() => ({
    initialized,
    authenticated,
    token,
    username,
    login: () => keycloak.login({redirectUri: window.location.origin + "/chats"}),
    logout: () => keycloak.logout({redirectUri: window.location.origin}),
    getToken: async () => {
      if (!keycloak.authenticated) return undefined;
      try {
        await keycloak.updateToken(30);
      } catch {
      }
      return keycloak.token;
    },
  }), [initialized, authenticated, token, username]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
