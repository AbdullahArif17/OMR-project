"use client";

import { useState, type FormEvent } from "react";
import { AdminConsole } from "@/components/admin-console";
import { useAuth } from "@/components/auth-provider";
import { LockIcon, LogoutIcon, MailIcon, ShieldIcon } from "@/components/icons";
import { Alert, Spinner } from "@/components/ui";

function AdminLogin() {
  const { signIn, signOut } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await signIn(email, password);
      // signIn resolves for any valid account; AdminConsole re-checks the role
      // and calls signOut for non-admins, so nothing else is needed here.
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Sign in failed.");
      setSubmitting(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center bg-canvas px-5">
      <div className="surface-card w-full max-w-md p-8">
        <span className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-slate-900 text-white"><ShieldIcon size={26} /></span>
        <h1 className="mt-5 text-center text-xl font-black text-slate-950">Admin console</h1>
        <p className="mt-2 text-center text-sm leading-6 text-slate-500">Restricted area. Sign in with the administrator account to manage teacher access.</p>
        <form className="mt-7 space-y-5" onSubmit={handleSubmit}>
          {error && <Alert>{error}</Alert>}
          <div>
            <label className="field-label" htmlFor="admin-email">Email address</label>
            <div className="relative"><MailIcon className="pointer-events-none absolute left-3.5 top-3.5 text-slate-400" size={18} /><input autoComplete="email" className="text-field pl-11" id="admin-email" onChange={(event) => setEmail(event.target.value)} required type="email" value={email} /></div>
          </div>
          <div>
            <label className="field-label" htmlFor="admin-password">Password</label>
            <div className="relative"><LockIcon className="pointer-events-none absolute left-3.5 top-3.5 text-slate-400" size={18} /><input autoComplete="current-password" className="text-field pl-11" id="admin-password" onChange={(event) => setPassword(event.target.value)} required type="password" value={password} /></div>
          </div>
          <button className="button-primary w-full" disabled={submitting} type="submit">{submitting ? <><Spinner /> Signing in…</> : <>Sign in</>}</button>
        </form>
        <button className="mt-4 w-full text-center text-xs font-semibold text-slate-400 hover:text-slate-600" onClick={() => void signOut()} type="button">Reset</button>
      </div>
    </main>
  );
}

export default function AdminPage() {
  const { user, loading, signOut } = useAuth();

  if (loading) {
    return (
      <main className="grid min-h-screen place-items-center bg-canvas">
        <div className="flex items-center text-brand-600"><Spinner className="h-6 w-6" /><span className="ml-3 text-sm font-semibold text-slate-500">Loading…</span></div>
      </main>
    );
  }

  if (!user) return <AdminLogin />;

  if (user.role.toLowerCase() !== "admin") {
    return (
      <main className="grid min-h-screen place-items-center bg-canvas px-5">
        <div className="surface-card w-full max-w-md p-8 text-center">
          <span className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-amber-50 text-amber-700"><ShieldIcon size={26} /></span>
          <h1 className="mt-5 text-xl font-black text-slate-950">Administrator access required</h1>
          <p className="mt-2 text-sm leading-6 text-slate-500">This account is not an administrator. Sign out and use the admin credentials.</p>
          <button className="button-secondary mt-6 w-full" onClick={() => void signOut()} type="button"><LogoutIcon size={17} /> Sign out</button>
        </div>
      </main>
    );
  }

  return <AdminConsole />;
}
