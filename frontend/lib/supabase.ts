import { createClient, type SupabaseClient } from "@supabase/supabase-js";

function isPlaceholder(value: string) {
  return value.includes("your-") || value.includes("your_");
}

const url = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
const publishableKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY?.trim();
const legacyAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim();
const key = publishableKey && !isPlaceholder(publishableKey)
  ? publishableKey
  : legacyAnonKey;

function legacyJwtRole(value: string) {
  const payload = value.split(".")[1];
  if (!payload) return null;
  try {
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
    const claims = JSON.parse(atob(padded)) as { role?: unknown };
    return typeof claims.role === "string" ? claims.role : null;
  } catch {
    return null;
  }
}

function isBrowserSafeKey(value: string) {
  if (value.startsWith("sb_publishable_")) return true;
  return legacyJwtRole(value) === "anon";
}

for (const candidate of [publishableKey, legacyAnonKey]) {
  if (candidate && (candidate.startsWith("sb_secret_") || legacyJwtRole(candidate) === "service_role")) {
    throw new Error(
      "Refusing to expose a Supabase secret/service-role key in the browser. Use a publishable or legacy anon key.",
    );
  }
}

export const isSupabaseConfigured = Boolean(
  url &&
    key &&
    !isPlaceholder(url) &&
    !isPlaceholder(key) &&
    isBrowserSafeKey(key) &&
    url.startsWith("https://"),
);

let instance: SupabaseClient | null = null;

export function getSupabase() {
  if (!isSupabaseConfigured || !url || !key) return null;
  if (!instance) {
    instance = createClient(url, key, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
      },
    });
  }
  return instance;
}
