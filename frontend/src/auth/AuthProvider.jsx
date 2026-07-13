import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { apiJson, configureApiSecurity } from "../api/client";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [csrf, setCsrf] = useState("");
  const [loading, setLoading] = useState(true);
  const [initialized, setInitialized] = useState(true);

  const clear = useCallback(() => {
    setUser(null);
    setCsrf("");
  }, []);

  const bootstrap = useCallback(async () => {
    try {
      const response = await fetch("/api/auth/session", { credentials: "same-origin" });
      const data = await response.json();
      setInitialized(data.auth_initialized !== false);
      if (data.authenticated) {
        setUser(data.user);
        setCsrf(data.csrf_token || "");
        return data.csrf_token || false;
      }
      clear();
      return false;
    } catch {
      clear();
      return false;
    } finally {
      setLoading(false);
    }
  }, [clear]);

  useEffect(() => { bootstrap(); }, [bootstrap]);
  useEffect(() => {
    configureApiSecurity({ csrf, refreshSession: bootstrap, onUnauthorized: clear });
  }, [csrf, bootstrap, clear]);

  const login = useCallback(async (email, password) => {
    const data = await apiJson("/api/auth/login", { method: "POST", body: { email, password } });
    setUser(data.user);
    setCsrf(data.csrf_token || "");
    return data;
  }, []);

  const logout = useCallback(async (all = false) => {
    await apiJson(all ? "/api/auth/logout-all" : "/api/auth/logout", { method: "POST" });
    clear();
  }, [clear]);

  const value = useMemo(() => ({ user, csrf, loading, initialized, login, logout, bootstrap }), [user, csrf, loading, initialized, login, logout, bootstrap]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
