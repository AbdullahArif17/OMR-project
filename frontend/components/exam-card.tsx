"use client";

import Link from "next/link";
import { CalendarIcon, ChevronRightIcon, ExamIcon, TrashIcon } from "@/components/icons";
import type { Exam } from "@/lib/types";
import { formatDate } from "@/lib/utils";

export function ExamCard({ exam, deleting, onDelete }: { exam: Exam; deleting?: boolean; onDelete: (exam: Exam) => void }) {
  return (
    <article className="surface-card group relative flex h-full flex-col overflow-hidden transition duration-200 hover:-translate-y-0.5 hover:border-brand-200 hover:shadow-lg">
      <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-brand-500 to-cyan-400 opacity-0 transition group-hover:opacity-100" />
      <div className="flex flex-1 flex-col p-5 sm:p-6">
        <div className="flex items-start justify-between gap-4">
          <span className="grid h-12 w-12 place-items-center rounded-2xl bg-brand-50 text-brand-600"><ExamIcon size={23} /></span>
          <div className="relative">
            <button aria-label={`Delete ${exam.name}`} className="grid h-9 w-9 place-items-center rounded-lg text-slate-400 transition hover:bg-rose-50 hover:text-rose-600" disabled={deleting} onClick={() => onDelete(exam)} title="Delete exam" type="button">
              {deleting ? <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-r-transparent" /> : <TrashIcon size={17} />}
            </button>
          </div>
        </div>
        <p className="mt-5 text-xs font-extrabold uppercase tracking-[0.15em] text-brand-600">{exam.subject || "General assessment"}</p>
        <h2 className="mt-2 line-clamp-2 text-lg font-black leading-6 text-slate-950">{exam.name}</h2>
        <div className="mt-4 flex flex-wrap gap-2 text-xs font-semibold text-slate-600">
          <span className="rounded-full bg-slate-100 px-2.5 py-1">{exam.total_questions} questions</span>
          <span className="rounded-full bg-slate-100 px-2.5 py-1">{exam.options_per_question} options</span>
        </div>
        <div className="mt-auto flex items-center gap-2 pt-6 text-xs text-slate-400"><CalendarIcon size={15} /><span>Created {formatDate(exam.created_at)}</span></div>
      </div>
      <Link className="flex items-center justify-between border-t border-slate-100 px-5 py-3.5 text-sm font-bold text-slate-700 transition hover:bg-brand-50 hover:text-brand-700 sm:px-6" href={`/exams/${exam.id}`}>
        Open exam workspace <ChevronRightIcon size={17} />
      </Link>
    </article>
  );
}
