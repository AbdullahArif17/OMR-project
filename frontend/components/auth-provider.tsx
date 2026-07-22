"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  api,
  getApiError,
  setAccessTokenProvider,
  setUnauthorizedHandler,
} from "@/lib/api";
import type { AccountUser, TokenPayload } from "@/lib/types";

const SESSION_KEY = "markwise-session";
const DEMO_SESSION_KEY = "markwise-demo-auth";
// Optional local-dev escape hatch for a backend running with AUTH_REQUIRED=false.
const allowDemo = process.env.NEXT_PUBLIC_ALLOW_DEMO === "true";

export interface AuthUser {
  id: string;
  name: string;
  role: string;
  isDemo: boolean;
}

interface StoredSession {
  accessToken: string;
  user: AuthUser;
}

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  allowDemo: boolean;
  signIn: (password: string) => Promise<void>;
  signOut: () => void;
  continueInDemo: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

function mapUser(account: AccountUser): AuthUser {
  return {
    id: account.id,
    name: account.name?.trim() || "Admin",
    role: "admin",
    isDemo: false,
  };
}

function toSession(payload: TokenPayload): StoredSession {
  return {
    accessToken: payload.access_token,
    user: mapUser(payload.user),
  };
}

function readStoredSession(): StoredSession | null {
  try {
    const raw = window.localStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<StoredSession>;
    if (parsed.accessToken && parsed.user) {
      return parsed as StoredSession;
    }
  } catch {
    // fall through to a clean slate
  }
  return null;
}

const demoUser: AuthUser = {
  id: "local-demo-admin",
  name: "Demo Admin",
  role: "admin",
  isDemo: true,
};

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const sessionRef = useRef<StoredSession | null>(null);

  const persist = useCallback((session: StoredSession | null) => {
    sessionRef.current = session;
    if (session) {
      window.localStorage.setItem(SESSION_KEY, JSON.stringify(session));
    } else {
      window.localStorage.removeItem(SESSION_KEY);
    }
  }, []);

  const clearSession = useCallback(() => {
    persist(null);
    window.localStorage.removeItem(DEMO_SESSION_KEY);
    setUser(null);
  }, [persist]);

  useEffect(() => {
    setAccessTokenProvider(() => sessionRef.current?.accessToken ?? null);
    // On a 401 we just log out since there's no refresh token
    setUnauthorizedHandler(async () => {
      clearSession();
      return null;
    });

    let mounted = true;
    function bootstrap() {
      if (allowDemo && window.localStorage.getItem(DEMO_SESSION_KEY) === "active") {
        if (mounted) setUser(demoUser);
        if (mounted) setLoading(false);
        return;
      }
      const stored = readStoredSession();
      if (stored) {
        persist(stored);
        if (mounted) setUser(stored.user);
      }
      if (mounted) setLoading(false);
    }

    bootstrap();

    return () => {
      mounted = false;
      setUnauthorizedHandler(null);
    };
  }, [clearSession, persist]);

  const signIn = useCallback(
    async (password: string) => {
      try {
        const session = toSession(await api.adminLogin(password));
        persist(session);
        setUser(session.user);
      } catch (error) {
        throw new Error(getApiError(error, "Sign in failed. Please check your password."));
      }
    },
    [persist],
  );

  const signOut = useCallback(() => {
    clearSession();
  }, [clearSession]);

  const continueInDemo = useCallback(() => {
    if (!allowDemo) return;
    window.localStorage.setItem(DEMO_SESSION_KEY, "active");
    setUser(demoUser);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ user, loading, allowDemo, signIn, signOut, continueInDemo }),
    [continueInDemo, loading, signIn, signOut, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider.");
  return context;
}
