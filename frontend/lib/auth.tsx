"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, setAuthToken, type User } from "./api";

const TOKEN_KEY = "cas.token";
const USER_KEY = "cas.user";

type Status = "loading" | "authenticated" | "anonymous";

interface AuthContextValue {
  status: Status;
  user: User | null;
  isAdmin: boolean;
  login: (email: string, password: string) => Promise<User>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function readStorage(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key: string, value: string | null) {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    // Storage unavailable (private mode, blocked): the session just won't persist.
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<Status>("loading");
  const [user, setUser] = useState<User | null>(null);

  const logout = useCallback(() => {
    setAuthToken(null);
    writeStorage(TOKEN_KEY, null);
    writeStorage(USER_KEY, null);
    setUser(null);
    setStatus("anonymous");
  }, []);

  // Restore a saved session, then confirm the token is still valid.
  useEffect(() => {
    const token = readStorage(TOKEN_KEY);
    let cancelled = false;
    const restore = async () => {
      if (!token) {
        if (!cancelled) setStatus("anonymous");
        return;
      }
      setAuthToken(token);
      try {
        const me = await api.me();
        if (cancelled) return;
        setUser(me);
        writeStorage(USER_KEY, JSON.stringify(me));
        setStatus("authenticated");
      } catch {
        if (!cancelled) logout();
      }
    };
    void restore();
    return () => {
      cancelled = true;
    };
  }, [logout]);

  useEffect(() => {
    const onUnauthorized = () => logout();
    window.addEventListener("cas:unauthorized", onUnauthorized);
    return () => window.removeEventListener("cas:unauthorized", onUnauthorized);
  }, [logout]);

  const login = useCallback(async (email: string, password: string) => {
    const res = await api.login(email, password);
    setAuthToken(res.access_token);
    writeStorage(TOKEN_KEY, res.access_token);
    writeStorage(USER_KEY, JSON.stringify(res.user));
    setUser(res.user);
    setStatus("authenticated");
    return res.user;
  }, []);

  const value = useMemo(
    () => ({ status, user, isAdmin: user?.role === "admin", login, logout }),
    [status, user, login, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
