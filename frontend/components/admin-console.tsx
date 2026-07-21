"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useAuth } from "@/components/auth-provider";
import { CheckIcon, LogoutIcon, PlusIcon, ShieldIcon, UsersIcon } from "@/components/icons";
import { Alert, EmptyState, Skeleton, Spinner } from "@/components/ui";
import { api, getApiError } from "@/lib/api";
import type { AccountUser } from "@/lib/types";

function formatDate(value: string) {
  return new Date(value).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export function AdminConsole() {
  const { user, signOut } = useAuth();
  const [teachers, setTeachers] = useState<AccountUser[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);

  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      setTeachers(await api.listTeachers());
    } catch (caught) {
      setLoadError(getApiError(caught, "Could not load teacher accounts."));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleCreate(event: FormEvent) {
    event.preventDefault();
    setFormError(null);
    setNotice(null);
    if (password.length < 12) {
      setFormError("Password must be at least 12 characters.");
      return;
    }
    setCreating(true);
    try {
      const created = await api.createTeacher({ email, name, password });
      setNotice(`Created ${created.email}.`);
      setEmail("");
      setName("");
      setPassword("");
      await load();
    } catch (caught) {
      setFormError(getApiError(caught, "Could not create the account."));
    } finally {
      setCreating(false);
    }
  }

  async function toggleActive(target: AccountUser) {
    setPendingId(target.id);
    setNotice(null);
    setLoadError(null);
    try {
      await api.setTeacherActive(target.id, !target.is_active);
      await load();
    } catch (caught) {
      setLoadError(getApiError(caught, "Could not update the account."));
    } finally {
      setPendingId(null);
    }
  }

  return (
    <div className="min-h-screen bg-canvas">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-5 py-4">
          <div className="flex items-center gap-3">
            <span className="grid h-10 w-10 place-items-center rounded-xl bg-slate-900 text-white"><ShieldIcon size={20} /></span>
            <div>
              <p className="text-sm font-black text-slate-950">Admin console</p>
              <p className="text-xs text-slate-500">{user?.email}</p>
            </div>
          </div>
          <button className="button-secondary" onClick={() => void signOut()} type="button"><LogoutIcon size={17} /> Sign out</button>
        </div>
      </header>

      <main className="mx-auto max-w-5xl space-y-8 px-5 py-8">
        <section className="surface-card p-6">
          <div className="flex items-center gap-3">
            <span className="grid h-10 w-10 place-items-center rounded-xl bg-brand-50 text-brand-600"><PlusIcon size={19} /></span>
            <div>
              <h2 className="text-lg font-extrabold text-slate-900">Add a teacher</h2>
              <p className="text-sm text-slate-500">New accounts sign in on the main site and can manage only their own exams.</p>
            </div>
          </div>
          <form className="mt-6 grid gap-4 sm:grid-cols-2" onSubmit={handleCreate}>
            {formError && <div className="sm:col-span-2"><Alert>{formError}</Alert></div>}
            {notice && <div className="sm:col-span-2"><Alert tone="success">{notice}</Alert></div>}
            <div>
              <label className="field-label" htmlFor="new-email">Email address</label>
              <input autoComplete="off" className="text-field" id="new-email" onChange={(event) => setEmail(event.target.value)} placeholder="teacher@school.edu" required type="email" value={email} />
            </div>
            <div>
              <label className="field-label" htmlFor="new-name">Name (optional)</label>
              <input autoComplete="off" className="text-field" id="new-name" onChange={(event) => setName(event.target.value)} placeholder="Jordan Lee" type="text" value={name} />
            </div>
            <div className="sm:col-span-2">
              <label className="field-label" htmlFor="new-password">Temporary password</label>
              <input autoComplete="new-password" className="text-field" id="new-password" minLength={12} onChange={(event) => setPassword(event.target.value)} placeholder="At least 12 characters" required type="text" value={password} />
              <p className="mt-1.5 text-xs text-slate-400">Share it securely; the teacher signs in with these credentials.</p>
            </div>
            <div className="sm:col-span-2">
              <button className="button-primary" disabled={creating} type="submit">{creating ? <><Spinner /> Creating…</> : <><PlusIcon size={17} /> Create account</>}</button>
            </div>
          </form>
        </section>

        <section>
          <div className="mb-4 flex items-center gap-3">
            <span className="grid h-9 w-9 place-items-center rounded-lg bg-slate-100 text-slate-600"><UsersIcon size={18} /></span>
            <h2 className="text-lg font-extrabold text-slate-900">Teacher accounts</h2>
          </div>
          {loadError && <Alert>{loadError}</Alert>}
          {teachers === null ? (
            <div className="space-y-3">{[0, 1, 2].map((key) => <Skeleton className="h-16" key={key} />)}</div>
          ) : teachers.length === 0 ? (
            <EmptyState description="Create a teacher account above to get started." icon={<UsersIcon size={24} />} title="No teachers yet" />
          ) : (
            <ul className="space-y-3">
              {teachers.map((teacher) => (
                <li className="surface-card flex flex-col gap-4 p-4 sm:flex-row sm:items-center sm:justify-between" key={teacher.id}>
                  <div className="min-w-0">
                    <p className="truncate font-bold text-slate-900">{teacher.name || teacher.email}</p>
                    <p className="truncate text-sm text-slate-500">{teacher.email}</p>
                    <p className="mt-1 text-xs text-slate-400">Added {formatDate(teacher.created_at)}</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className={teacher.is_active ? "inline-flex items-center gap-1 rounded-full bg-emerald-50 px-3 py-1 text-xs font-bold text-emerald-700" : "inline-flex items-center gap-1 rounded-full bg-slate-100 px-3 py-1 text-xs font-bold text-slate-500"}>
                      {teacher.is_active ? <><CheckIcon size={13} /> Active</> : "Disabled"}
                    </span>
                    <button className="button-secondary" disabled={pendingId === teacher.id} onClick={() => void toggleActive(teacher)} type="button">
                      {pendingId === teacher.id ? <Spinner className="h-4 w-4" /> : teacher.is_active ? "Disable" : "Enable"}
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </main>
    </div>
  );
}
