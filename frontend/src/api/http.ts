import {useAuth} from "../auth/AuthContext";

export function useAuthedFetch() {
  const auth = useAuth();
  const baseUrl = import.meta.env.VITE_BACKEND_URL ?? "http://localhost:5000";

  return async (path: string, init: RequestInit = {}) => {
    const token = await auth.getToken();
    const headers = new Headers(init.headers);

    if (token) headers.set("Authorization", `Bearer ${token}`);
    if (!headers.has("Content-Type") && init.body) headers.set("Content-Type", "application/json");

    const res = await fetch(`${baseUrl}${path}`, {...init, headers});
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`HTTP ${res.status}: ${text}`);
    }
    return res;
  };
}
