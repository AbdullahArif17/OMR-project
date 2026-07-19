import Link from "next/link";
import { ChevronRightIcon, EyeIcon } from "@/components/icons";
import type { Result } from "@/lib/types";
import { cn, formatDate, getGrade, gradeTone, studentClass, studentName, studentRoll } from "@/lib/utils";

export function ResultsTable({ results }: { results: Result[] }) {
  return (
    <div className="surface-card overflow-hidden">
      <div className="hidden overflow-x-auto md:block">
        <table className="min-w-full divide-y divide-slate-200">
          <thead className="bg-slate-50/80">
            <tr>
              {[
                ["Roll no.", "text-left"],
                ["Student", "text-left"],
                ["Class", "text-left"],
                ["Score", "text-right"],
                ["Percentage", "text-right"],
                ["Grade", "text-center"],
                ["Scanned", "text-left"],
                ["", "text-right"],
              ].map(([label, align], index) => <th className={cn("whitespace-nowrap px-5 py-3.5 text-[11px] font-extrabold uppercase tracking-[0.12em] text-slate-500", align)} key={`${label}-${index}`} scope="col">{label}</th>)}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 bg-white">
            {results.map((result) => {
              const tone = gradeTone(result.percentage);
              return (
                <tr className="transition hover:bg-slate-50/80" key={result.id}>
                  <td className="whitespace-nowrap px-5 py-4 text-sm font-semibold text-slate-600">{studentRoll(result)}</td>
                  <td className="px-5 py-4"><p className="max-w-52 truncate text-sm font-extrabold text-slate-900">{studentName(result)}</p><p className="mt-0.5 max-w-52 truncate text-xs text-slate-400">{result.filename || result.source_file || "Scanned sheet"}</p></td>
                  <td className="whitespace-nowrap px-5 py-4 text-sm text-slate-500">{studentClass(result)}</td>
                  <td className="whitespace-nowrap px-5 py-4 text-right text-sm font-black text-slate-900">{result.score}<span className="font-semibold text-slate-400">/{result.total}</span></td>
                  <td className="whitespace-nowrap px-5 py-4 text-right"><span className={cn("text-sm font-black", tone.text)}>{Number(result.percentage).toFixed(1)}%</span></td>
                  <td className="px-5 py-4 text-center"><span className={cn("inline-flex min-w-8 justify-center rounded-full px-2.5 py-1 text-xs font-black ring-1 ring-inset", tone.badge)}>{getGrade(result.percentage)}</span></td>
                  <td className="whitespace-nowrap px-5 py-4 text-xs text-slate-500">{formatDate(result.scanned_at)}</td>
                  <td className="px-5 py-4 text-right"><Link aria-label={`View result for ${studentName(result)}`} className="inline-grid h-9 w-9 place-items-center rounded-lg text-slate-400 transition hover:bg-brand-50 hover:text-brand-700" href={`/results/${result.id}`}><EyeIcon size={17} /></Link></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="divide-y divide-slate-100 md:hidden">
        {results.map((result) => {
          const tone = gradeTone(result.percentage);
          return (
            <Link className="block p-4 transition hover:bg-slate-50" href={`/results/${result.id}`} key={result.id}>
              <div className="flex items-start justify-between gap-4"><div className="min-w-0"><p className="truncate text-sm font-black text-slate-900">{studentName(result)}</p><p className="mt-1 truncate text-xs text-slate-500">{studentRoll(result)} · {studentClass(result)}</p></div><span className={cn("rounded-full px-2.5 py-1 text-xs font-black ring-1 ring-inset", tone.badge)}>{getGrade(result.percentage)}</span></div>
              <div className="mt-4 flex items-end justify-between"><div><p className="text-lg font-black text-slate-950">{result.score}<span className="text-sm text-slate-400">/{result.total}</span></p><p className={cn("text-xs font-extrabold", tone.text)}>{Number(result.percentage).toFixed(1)}%</p></div><span className="inline-flex items-center gap-1 text-xs font-extrabold text-brand-600">View details <ChevronRightIcon size={14} /></span></div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
