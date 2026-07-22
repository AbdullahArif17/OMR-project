"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/components/auth-provider";
import {
  ChartIcon,
  CloseIcon,
  DashboardIcon,
  LogoutIcon,
  MenuIcon,
  PlusIcon,
  ShieldIcon,
} from "@/components/icons";
import { Logo } from "@/components/logo";
import { Spinner } from "@/components/ui";
import { cn, getInitials } from "@/lib/utils";

const navigation = [
  { href: "/dashboard", label: "Dashboard", icon: DashboardIcon, exact: true },
  { href: "/exams/create", label: "Create exam", icon: PlusIcon, exact: true },
];

function WorkspaceNavigation({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <nav className="mt-8" aria-label="Workspace navigation">
      <p className="px-3 text-[11px] font-extrabold uppercase tracking-[0.16em] text-slate-400">Workspace</p>
      <ul className="mt-3 space-y-1">
        {navigation.map((item) => {
          const active = item.exact ? pathname === item.href : pathname.startsWith(item.href);
          const Icon = item.icon;
          return (
            <li key={item.href}>
              <Link
                className={cn(
                  "flex items-center gap-3 rounded-xl px-3 py-3 text-sm font-bold transition",
                  active ? "bg-brand-50 text-brand-700" : "text-slate-600 hover:bg-slate-100 hover:text-slate-950",
                )}
                href={item.href}
                onClick={onNavigate}
              >
                <Icon size={19} /> {item.label}
              </Link>
            </li>
          );
        })}
      </ul>
      <p className="mt-8 px-3 text-[11px] font-extrabold uppercase tracking-[0.16em] text-slate-400">Quick guide</p>
      <div className="mx-2 mt-3 rounded-2xl bg-[#17213b] p-4 text-white">
        <span className="grid h-9 w-9 place-items-center rounded-xl bg-white/10 text-brand-200"><ChartIcon size={19} /></span>
        <p className="mt-4 text-sm font-extrabold">Need results?</p>
        <p className="mt-1 text-xs leading-5 text-slate-300">Open an exam from the dashboard to scan sheets or review its analytics.</p>
      </div>
    </nav>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const { user, loading, signOut } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);

  useEffect(() => {
    if (!loading && !user) router.replace("/admin");
  }, [loading, router, user]);

  async function handleSignOut() {
    setSigningOut(true);
    await signOut();
    router.replace("/admin");
  }

  if (loading || !user) {
    return (
      <main className="grid min-h-screen place-items-center bg-canvas">
        <div className="text-center text-brand-600"><Spinner className="h-7 w-7" /><p className="mt-4 text-sm font-bold text-slate-500">Preparing your workspace…</p></div>
      </main>
    );
  }

  return (
    <div className="min-h-screen bg-canvas">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[272px] border-r border-slate-200 bg-white lg:flex lg:flex-col">
        <div className="px-6 pt-6"><Logo href="/dashboard" /></div>
        <div className="flex-1 overflow-y-auto px-4"><WorkspaceNavigation /></div>
        <div className="border-t border-slate-200 p-4">
          {user.isDemo && <div className="mb-3 flex items-center gap-2 rounded-xl bg-amber-50 px-3 py-2 text-xs font-bold text-amber-700"><ShieldIcon size={16} /> Local demo auth</div>}
          <div className="flex items-center gap-3 px-2 py-2">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-brand-100 text-sm font-black text-brand-700">{getInitials(user.name)}</span>
            <div className="min-w-0 flex-1"><p className="truncate text-sm font-bold text-slate-900">{user.name}</p><p className="truncate text-xs capitalize text-slate-500">{user.role}</p></div>
            <button aria-label="Sign out" className="grid h-9 w-9 place-items-center rounded-lg text-slate-400 transition hover:bg-rose-50 hover:text-rose-600" disabled={signingOut} onClick={handleSignOut} title="Sign out" type="button">{signingOut ? <Spinner className="h-4 w-4" /> : <LogoutIcon size={18} />}</button>
          </div>
        </div>
      </aside>

      <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-slate-200/80 bg-white/90 px-4 backdrop-blur lg:hidden">
        <Logo compact href="/dashboard" />
        <button aria-expanded={mobileOpen} aria-label="Open navigation" className="grid h-10 w-10 place-items-center rounded-xl border border-slate-200 bg-white text-slate-700" onClick={() => setMobileOpen(true)} type="button"><MenuIcon /></button>
      </header>

      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button aria-label="Close navigation" className="absolute inset-0 bg-slate-950/45 backdrop-blur-sm" onClick={() => setMobileOpen(false)} type="button" />
          <aside className="absolute inset-y-0 right-0 flex w-[min(88vw,340px)] animate-fade-in flex-col bg-white p-4 shadow-2xl">
            <div className="flex items-center justify-between px-2 py-2"><Logo href="/dashboard" /><button aria-label="Close navigation" className="grid h-10 w-10 place-items-center rounded-xl text-slate-500 hover:bg-slate-100" onClick={() => setMobileOpen(false)} type="button"><CloseIcon /></button></div>
            <div className="flex-1 overflow-y-auto"><WorkspaceNavigation onNavigate={() => setMobileOpen(false)} /></div>
            <div className="border-t border-slate-200 pt-4">
              {user.isDemo && <div className="mb-3 flex items-center gap-2 rounded-xl bg-amber-50 px-3 py-2 text-xs font-bold text-amber-700"><ShieldIcon size={16} /> Local demo auth</div>}
              <div className="flex items-center gap-3 px-2"><span className="grid h-10 w-10 place-items-center rounded-xl bg-brand-100 text-sm font-black text-brand-700">{getInitials(user.name)}</span><div className="min-w-0 flex-1"><p className="truncate text-sm font-bold">{user.name}</p><p className="truncate text-xs text-slate-500">{user.role}</p></div><button aria-label="Sign out" className="grid h-10 w-10 place-items-center rounded-xl text-slate-500 hover:bg-rose-50 hover:text-rose-600" onClick={handleSignOut} type="button"><LogoutIcon /></button></div>
            </div>
          </aside>
        </div>
      )}

      <div className="lg:pl-[272px]">
        <div className="mx-auto w-full max-w-[1440px] px-4 py-7 sm:px-7 sm:py-9 lg:px-10 lg:py-10">{children}</div>
      </div>
    </div>
  );
}
