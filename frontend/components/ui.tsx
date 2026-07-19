import type { ReactNode } from "react";
import { AlertIcon, InfoIcon, RefreshIcon } from "@/components/icons";
import { cn } from "@/lib/utils";

export function Spinner({ className = "h-5 w-5" }: { className?: string }) {
  return <span aria-hidden="true" className={cn("inline-block animate-spin rounded-full border-2 border-current border-r-transparent", className)} />;
}

export function Alert({ children, tone = "error", title }: { children: ReactNode; tone?: "error" | "info" | "success"; title?: string }) {
  const styles = {
    error: "border-rose-200 bg-rose-50 text-rose-800",
    info: "border-blue-200 bg-blue-50 text-blue-800",
    success: "border-emerald-200 bg-emerald-50 text-emerald-800",
  }[tone];
  const Icon = tone === "error" ? AlertIcon : InfoIcon;
  return (
    <div className={cn("flex gap-3 rounded-xl border px-4 py-3 text-sm", styles)} role={tone === "error" ? "alert" : "status"}>
      <Icon className="mt-0.5 shrink-0" size={18} />
      <div>
        {title && <p className="font-bold">{title}</p>}
        <div className={title ? "mt-0.5" : ""}>{children}</div>
      </div>
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden="true" className={cn("animate-pulse-soft rounded-xl bg-slate-200/80", className)} />;
}

export function EmptyState({ icon, title, description, action }: { icon: ReactNode; title: string; description: string; action?: ReactNode }) {
  return (
    <div className="surface-card flex min-h-72 flex-col items-center justify-center px-6 py-12 text-center">
      <div className="grid h-14 w-14 place-items-center rounded-2xl bg-brand-50 text-brand-600">{icon}</div>
      <h2 className="mt-5 text-lg font-extrabold text-slate-900">{title}</h2>
      <p className="mt-2 max-w-md text-sm leading-6 text-slate-500">{description}</p>
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}

export function RetryButton({ onClick }: { onClick: () => void }) {
  return <button className="button-secondary mt-4" onClick={onClick} type="button"><RefreshIcon size={17} /> Try again</button>;
}

export function PageTitle({ eyebrow, title, description, actions }: { eyebrow?: string; title: string; description?: string; actions?: ReactNode }) {
  return (
    <div className="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
      <div>
        {eyebrow && <p className="mb-2 text-xs font-extrabold uppercase tracking-[0.18em] text-brand-600">{eyebrow}</p>}
        <h1 className="text-2xl font-black tracking-tight text-slate-950 sm:text-3xl">{title}</h1>
        {description && <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500 sm:text-base">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap gap-3">{actions}</div>}
    </div>
  );
}

export function StatCard({ label, value, note, icon, accent = "brand" }: { label: string; value: string | number; note?: string; icon: ReactNode; accent?: "brand" | "emerald" | "amber" | "rose" }) {
  const tone = {
    brand: "bg-brand-50 text-brand-600",
    emerald: "bg-emerald-50 text-emerald-600",
    amber: "bg-amber-50 text-amber-600",
    rose: "bg-rose-50 text-rose-600",
  }[accent];
  return (
    <div className="surface-card p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-slate-500">{label}</p>
          <p className="mt-2 text-2xl font-black tracking-tight text-slate-950">{value}</p>
          {note && <p className="mt-1 text-xs text-slate-400">{note}</p>}
        </div>
        <span className={cn("grid h-11 w-11 place-items-center rounded-xl", tone)}>{icon}</span>
      </div>
    </div>
  );
}
