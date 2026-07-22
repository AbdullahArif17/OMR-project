"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/auth-provider";
import { LockIcon, ShieldIcon } from "@/components/icons";
import { Alert, Spinner } from "@/components/ui";

export default function AdminLogin() {
  const router = useRouter();
  const { signIn, loading, user } = useAuth();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (loading) {
    return (
      <main className="grid min-h-screen place-items-center bg-canvas">
        <div className="flex items-center text-brand-600"><Spinner className="h-6 w-6" /><span className="ml-3 text-sm font-semibold text-slate-500">Loading…</span></div>
      </main>
    );
  }

  // If already authenticated, redirect to dashboard
  if (user) {
    router.replace("/dashboard");
    return null;
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await signIn(password);
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
        <h1 className="mt-5 text-center text-xl font-black text-slate-950">System Access</h1>
        <p className="mt-2 text-center text-sm leading-6 text-slate-500">Restricted area. Please enter the master password.</p>
        <form className="mt-7 space-y-5" onSubmit={handleSubmit}>
          {error && <Alert>{error}</Alert>}
          <div>
            <label className="field-label" htmlFor="admin-password">Password</label>
            <div className="relative"><LockIcon className="pointer-events-none absolute left-3.5 top-3.5 text-slate-400" size={18} /><input autoComplete="current-password" className="text-field pl-11" id="admin-password" onChange={(event) => setPassword(event.target.value)} required type="password" value={password} /></div>
          </div>
          <button className="button-primary w-full" disabled={submitting} type="submit">{submitting ? <><Spinner /> Verifying…</> : <>Enter System</>}</button>
        </form>
      </div>
    </main>
  );
}
