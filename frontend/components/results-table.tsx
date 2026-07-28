import Link from "next/link";
import { ChevronRightIcon, EyeIcon } from "@/components/icons";
import type { Result } from "@/lib/types";
import { cn, formatDate, getGrade, gradeTone, studentClass, studentName, studentRoll } from "@/lib/utils";

/** Pencil icon for editing */
function EditIcon({ size = 17 }: { size?: number }) {
  return (
    <svg aria-hidden="true" fill="none" height={size} viewBox="0 0 24 24" width={size} xmlns="http://www.w3.org/2000/svg">
      <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} />
    </svg>
  );
}

interface ResultsTableProps {
  results: Result[];
  onEdit?: (result: Result) => void;
}

export function ResultsTable({ results, onEdit }: ResultsTableProps) {
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
                  <td className="px-5 py-4 text-right">
                    <div className="flex items-center justify-end gap-1">
                      {onEdit && (
                        <button
                          aria-label={`Edit result for ${studentName(result)}`}
                          className="inline-grid h-9 w-9 place-items-center rounded-lg text-slate-400 transition hover:bg-amber-50 hover:text-amber-700"
                          onClick={() => onEdit(result)}
                          type="button"
                        >
                          <EditIcon size={16} />
                        </button>
                      )}
                      <Link aria-label={`View result for ${studentName(result)}`} className="inline-grid h-9 w-9 place-items-center rounded-lg text-slate-400 transition hover:bg-brand-50 hover:text-brand-700" href={`/results/${result.id}`}><EyeIcon size={17} /></Link>
                    </div>
                  </td>
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
            <div className="p-4" key={result.id}>
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <p className="truncate text-sm font-black text-slate-900">{studentName(result)}</p>
                  <p className="mt-1 truncate text-xs text-slate-500">{studentRoll(result)} · {studentClass(result)}</p>
                </div>
                <span className={cn("rounded-full px-2.5 py-1 text-xs font-black ring-1 ring-inset", tone.badge)}>{getGrade(result.percentage)}</span>
              </div>
              <div className="mt-4 flex items-end justify-between">
                <div>
                  <p className="text-lg font-black text-slate-950">{result.score}<span className="text-sm text-slate-400">/{result.total}</span></p>
                  <p className={cn("text-xs font-extrabold", tone.text)}>{Number(result.percentage).toFixed(1)}%</p>
                </div>
                <div className="flex items-center gap-2">
                  {onEdit && (
                    <button
                      className="inline-flex items-center gap-1 rounded-lg border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs font-extrabold text-amber-700 transition hover:bg-amber-100"
                      onClick={() => onEdit(result)}
                      type="button"
                    >
                      <EditIcon size={13} /> Edit
                    </button>
                  )}
                  <Link className="inline-flex items-center gap-1 text-xs font-extrabold text-brand-600" href={`/results/${result.id}`}>View details <ChevronRightIcon size={14} /></Link>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
