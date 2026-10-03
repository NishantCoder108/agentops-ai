import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { currentUser, login as loginRequest } from "../api/auth";
import type { User } from "../api/types";
import { readToken, UNAUTHORIZED_EVENT, writeToken } from "./storage";

type AuthStatus = "loading" | "anonymous" | "authenticated";

type AuthContextValue = {
  status: AuthStatus;
  user: User | null;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => readToken());
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<AuthStatus>(token ? "loading" : "anonymous");

  useEffect(() => {
    const onUnauthorized = () => {
      setToken(null);
      setUser(null);
      setStatus("anonymous");
    };
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, []);

  useEffect(() => {
    if (!token) {
      setUser(null);
      setStatus("anonymous");
      return;
    }
    let cancelled = false;
    setStatus("loading");
    currentUser()
      .then((next) => {
        if (!cancelled) {
          setUser(next);
          setStatus("authenticated");
        }
      })
      .catch(() => {
        if (!cancelled) {
          writeToken(null);
          setToken(null);
          setUser(null);
          setStatus("anonymous");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      async signIn(email: string, password: string) {
        const response = await loginRequest(email, password);
        writeToken(response.access_token);
        setUser(response.user);
        setToken(response.access_token);
        setStatus("authenticated");
      },
      signOut() {
        writeToken(null);
        setToken(null);
        setUser(null);
        setStatus("anonymous");
      },
    }),
    [status, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return value;
}
