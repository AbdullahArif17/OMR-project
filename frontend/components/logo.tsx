import Link from "next/link";
import { cn } from "@/lib/utils";

export function Logo({ href = "/", compact = false, light = false }: { href?: string; compact?: boolean; light?: boolean }) {
  return (
    <Link className="inline-flex items-center gap-3 rounded-lg" href={href} aria-label="Markwise home">
      <span className="relative grid h-10 w-10 shrink-0 place-items-center overflow-hidden rounded-xl bg-brand-600 shadow-sm">
        <span className="absolute -right-2 -top-2 h-6 w-6 rounded-full bg-brand-400/60" />
        <svg aria-hidden="true" className="relative" fill="none" height="24" viewBox="0 0 24 24" width="24">
          <path d="M6.5 4.5h11v15h-11z" stroke="white" strokeWidth="1.7" />
          <circle cx="9.3" cy="8" fill="white" r="1.35" />
          <circle cx="9.3" cy="12" fill="white" r="1.35" />
          <circle cx="9.3" cy="16" fill="white" r="1.35" />
          <path d="m12.5 15.8 1.45 1.35 3-3.2" stroke="#c7d2fe" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" />
        </svg>
      </span>
      {!compact && (
        <span className={cn("text-xl font-black tracking-tight", light ? "text-white" : "text-ink")}>Markwise</span>
      )}
    </Link>
  );
}
