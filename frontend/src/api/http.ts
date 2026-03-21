import {useCallback} from "react";

import {useAuth} from "../auth/AuthContext";

export function useAuthedFetchBase(baseUrl: string) {
  const auth = useAuth();
  const getToken = auth.getToken;

  return useCallback(async (path: string, init: RequestInit = {}) => {
    const token = await getToken();
    const headers = new Headers(init.headers);

    if (token) headers.set("Authorization", `Bearer ${token}`);
    const body = init.body;
    const isFormData = typeof FormData !== "undefined" && body instanceof FormData;
    if (!headers.has("Content-Type") && body && !isFormData) headers.set("Content-Type", "application/json");

    const res = await fetch(`${baseUrl}${path}`, {...init, headers});
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`HTTP ${res.status}: ${text}`);
    }
    return res;
  }, [getToken, baseUrl]);
}

export function useAuthedFetch() {
  const baseUrl = import.meta.env.VITE_BACKEND_URL ?? "http://localhost:5000";
  return useAuthedFetchBase(baseUrl);
}
