"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { User } from "@supabase/supabase-js";
import { setAccessTokenProvider } from "@/lib/api";
import { getSupabase, isSupabaseConfigured } from "@/lib/supabase";

const DEMO_SESSION_KEY = "markwise-demo-auth";

export interface AuthUser {
  id: string;
  email: string;
  name: string;
  role: string;
  isDemo: boolean;
}

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  isConfigured: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  continueInDemo: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

function decodeTokenClaims(accessToken?: string): Record<string, unknown> {
  const payload = accessToken?.split(".")[1];
  if (!payload) return {};
  try {
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
    const claims = JSON.parse(atob(padded));
    return claims && typeof claims === "object" ? claims as Record<string, unknown> : {};
  } catch {
    return {};
  }
}

function roleValues(value: unknown): string[] {
  if (typeof value === "string") return value.split(",");
  if (Array.isArray(value)) {
    return value.filter((role): role is string => typeof role === "string");
  }
  return [];
}

function mapUser(user: User, accessToken?: string): AuthUser {
  const profile = user.user_metadata as Record<string, unknown>;
  const trustedMetadata = user.app_metadata as Record<string, unknown>;
  const claims = decodeTokenClaims(accessToken);
  const claimsMetadata = claims.app_metadata && typeof claims.app_metadata === "object"
    ? claims.app_metadata as Record<string, unknown>
    : {};
  const email = user.email || "teacher@school.local";
  const roleCandidates = [
    ...roleValues(trustedMetadata.role),
    ...roleValues(trustedMetadata.roles),
    ...roleValues(claimsMetadata.role),
    ...roleValues(claimsMetadata.roles),
    ...roleValues(claims.user_role),
    ...roleValues(claims.roles),
    ...roleValues(claims.role),
  ].map((role) => role.trim().toLowerCase());
  const role = roleCandidates.includes("admin")
    ? "admin"
    : roleCandidates.includes("teacher")
      ? "teacher"
      : "user";
  return {
    id: user.id,
    email,
    name:
      (typeof profile.full_name === "string" && profile.full_name) ||
      (typeof profile.name === "string" && profile.name) ||
      email.split("@")[0],
    role,
    isDemo: false,
  };
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

  useEffect(() => {
    const supabase = getSupabase();
    setAccessTokenProvider(async () => {
      if (!supabase) return null;
      const { data } = await supabase.auth.getSession();
      return data.session?.access_token ?? null;
    });

    if (!supabase) {
      const hasDemoSession = window.localStorage.getItem(DEMO_SESSION_KEY) === "active";
      setUser(hasDemoSession ? demoUser : null);
      setLoading(false);
      return;
    }

    let mounted = true;
    void supabase.auth.getSession().then(({ data }) => {
      if (!mounted) return;
      setUser(data.session?.user ? mapUser(data.session.user, data.session.access_token) : null);
      setLoading(false);
    });
    const { data: listener } = supabase.auth.onAuthStateChange((_event, session) => {
      if (!mounted) return;
      setUser(session?.user ? mapUser(session.user, session.access_token) : null);
      setLoading(false);
    });
    return () => {
      mounted = false;
      listener.subscription.unsubscribe();
    };
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    const supabase = getSupabase();
    if (!supabase) {
      throw new Error("Supabase is not configured. Use the local demo button instead.");
    }
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) throw new Error(error.message);
  }, []);

  const signOut = useCallback(async () => {
    const supabase = getSupabase();
    if (supabase) await supabase.auth.signOut();
    window.localStorage.removeItem(DEMO_SESSION_KEY);
    setUser(null);
  }, []);

  const continueInDemo = useCallback(() => {
    if (isSupabaseConfigured) return;
    window.localStorage.setItem(DEMO_SESSION_KEY, "active");
    setUser(demoUser);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      loading,
      isConfigured: isSupabaseConfigured,
      signIn,
      signOut,
      continueInDemo,
    }),
    [continueInDemo, loading, signIn, signOut, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider.");
  return context;
}
