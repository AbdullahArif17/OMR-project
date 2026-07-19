"use client";

import Link from "next/link";
import { CheckIcon, ChevronRightIcon, EyeIcon, FileIcon } from "@/components/icons";
import type { Result } from "@/lib/types";
import { breakdownRows, cn, gradeTone, isCorrect, studentName, studentRoll } from "@/lib/utils";

export function ScanResultCard({ result }: { result: Result }) {
  const tone = gradeTone(result.percentage);
  const rows = breakdownRows(result);
  const passed = result.percentage >= 60;
  const scoreIconTone = passed
    ? "bg-emerald-50 text-emerald-600"
    : result.percentage >= 40
      ? "bg-amber-50 text-amber-600"
      : "bg-rose-50 text-rose-600";
  return (
    <article className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
      <div className="flex flex-col gap-5 p-5 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-4">
          <span className={cn("grid h-12 w-12 shrink-0 place-items-center rounded-2xl", scoreIconTone)}><CheckIcon size={22} /></span>
          <div className="min-w-0"><h3 className="truncate font-black text-slate-950">{studentName(result)}</h3><p className="mt-1 flex items-center gap-1.5 truncate text-xs text-slate-500"><FileIcon size={14} /> {studentRoll(result) !== "—" ? `Roll ${studentRoll(result)} · ` : ""}{result.filename || result.source_file || "Scanned sheet"}</p></div>
        </div>
        <div className="flex items-center gap-4 sm:justify-end">
          <div className="text-right"><p className="text-xl font-black text-slate-950">{result.score}<span className="text-sm font-bold text-slate-400">/{result.total}</span></p><p className={cn("text-xs font-extrabold", tone.text)}>{Number(result.percentage).toFixed(1)}%</p></div>
          <span className={cn("rounded-full px-3 py-1.5 text-xs font-extrabold ring-1 ring-inset", tone.badge)}>{passed ? "Pass" : "Fail"}</span>
        </div>
      </div>
      {rows.length > 0 && (
        <details className="group border-t border-slate-100">
          <summary className="flex cursor-pointer list-none items-center justify-between px-5 py-3.5 text-sm font-bold text-slate-600 transition hover:bg-slate-50 hover:text-slate-900"><span className="inline-flex items-center gap-2"><EyeIcon size={17} /> Question breakdown</span><ChevronRightIcon className="transition group-open:rotate-90" size={17} /></summary>
          <div className="border-t border-slate-100 bg-slate-50/70 p-4">
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-5">
              {rows.map((row, index) => {
                const correct = isCorrect(row);
                const student = row.student ?? row.selected_answer ?? "—";
                const expected = row.correct ?? row.correct_answer ?? "—";
                return <div className={cn("rounded-lg border px-3 py-2 text-xs", correct ? "border-emerald-200 bg-emerald-50" : "border-rose-200 bg-rose-50")} key={`${row.question}-${index}`}><div className="flex items-center justify-between"><span className="font-bold text-slate-500">Q{row.question}</span><span className={cn("font-black", correct ? "text-emerald-700" : "text-rose-700")}>{student}</span></div>{!correct && <p className="mt-1 text-[11px] text-slate-500">Correct: <strong>{expected}</strong></p>}</div>;
              })}
            </div>
          </div>
        </details>
      )}
      <div className="border-t border-slate-100 px-5 py-3 text-right"><Link className="inline-flex items-center gap-1 text-xs font-extrabold text-brand-600 hover:text-brand-800" href={`/results/${result.id}`}>Open saved result <ChevronRightIcon size={14} /></Link></div>
    </article>
  );
}
