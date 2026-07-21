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
  email: string;
  name: string;
  role: string;
  isDemo: boolean;
}

interface StoredSession {
  accessToken: string;
  refreshToken: string;
  user: AuthUser;
}

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  allowDemo: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  continueInDemo: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

function mapUser(account: AccountUser): AuthUser {
  const email = account.email || "teacher@school.local";
  return {
    id: account.id,
    email,
    name: account.name?.trim() || email.split("@")[0],
    role: account.role || "teacher",
    isDemo: false,
  };
}

function toSession(payload: TokenPayload): StoredSession {
  return {
    accessToken: payload.access_token,
    refreshToken: payload.refresh_token,
    user: mapUser(payload.user),
  };
}

function readStoredSession(): StoredSession | null {
  try {
    const raw = window.localStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<StoredSession>;
    if (parsed.accessToken && parsed.refreshToken && parsed.user) {
      return parsed as StoredSession;
    }
  } catch {
    // fall through to a clean slate
  }
  return null;
}

const demoUser: AuthUser = {
  id: "local-demo-teacher",
  email: "teacher@demo.local",
  name: "Demo Teacher",
  role: "teacher",
  isDemo: true,
};

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  // A ref backs the synchronous token accessor used by the axios interceptors.
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
    // On a 401 the client asks us to rotate the refresh token once; failure
    // clears the session so the user is bounced to the sign-in screen.
    setUnauthorizedHandler(async () => {
      const current = sessionRef.current;
      if (!current) return null;
      try {
        const rotated = toSession(await api.refreshSession(current.refreshToken));
        persist(rotated);
        setUser(rotated.user);
        return rotated.accessToken;
      } catch {
        clearSession();
        return null;
      }
    });

    let mounted = true;
    async function bootstrap() {
      if (allowDemo && window.localStorage.getItem(DEMO_SESSION_KEY) === "active") {
        if (mounted) setUser(demoUser);
        return;
      }
      const stored = readStoredSession();
      if (!stored) return;
      // Rotate on load so a resumed session never rides a stale refresh token.
      try {
        const rotated = toSession(await api.refreshSession(stored.refreshToken));
        if (!mounted) return;
        persist(rotated);
        setUser(rotated.user);
      } catch {
        if (mounted) clearSession();
      }
    }

    void bootstrap().finally(() => {
      if (mounted) setLoading(false);
    });

    return () => {
      mounted = false;
      setUnauthorizedHandler(null);
    };
  }, [clearSession, persist]);

  const signIn = useCallback(
    async (email: string, password: string) => {
      try {
        const session = toSession(await api.login(email, password));
        persist(session);
        setUser(session.user);
      } catch (error) {
        throw new Error(getApiError(error, "Sign in failed. Please try again."));
      }
    },
    [persist],
  );

  const signOut = useCallback(async () => {
    const current = sessionRef.current;
    if (current) {
      try {
        await api.logout(current.refreshToken);
      } catch {
        // best effort: revoke server-side but always clear locally
      }
    }
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
