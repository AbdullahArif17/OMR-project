"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/auth-provider";
import { ShieldIcon } from "@/components/icons";
import { Alert, Spinner } from "@/components/ui";

export default function AdminLogin() {
  const router = useRouter();
  const { signIn, loading, user } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (loading) {
    return (
      <main className="grid min-h-screen place-items-center bg-canvas">
        <div className="flex items-center text-brand-600"><Spinner className="h-6 w-6" /><span className="ml-3 text-sm font-semibold text-slate-500">Loading…</span></div>
      </main>
    );
  }

  if (user) {
    router.replace("/dashboard");
    return null;
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await signIn();
      router.push("/dashboard");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Sign in failed.");
      setSubmitting(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center bg-canvas px-5">
      <div className="surface-card w-full max-w-md p-8">
        <span className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-slate-900 text-white"><ShieldIcon size={26} /></span>
        <h1 className="mt-5 text-center text-xl font-black text-slate-950">Markwise</h1>
        <p className="mt-2 text-center text-sm leading-6 text-slate-500">Click below to access the system.</p>
        <form className="mt-7 space-y-5" onSubmit={handleSubmit}>
          {error && <Alert>{error}</Alert>}
          <button className="button-primary w-full" disabled={submitting} type="submit">
            {submitting ? <><Spinner /> Signing in…</> : <>Enter System</>}
          </button>
        </form>
      </div>
    </main>
  );
}
