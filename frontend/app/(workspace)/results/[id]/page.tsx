"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeftIcon, CalendarIcon, CheckIcon, ExamIcon, FileIcon, UsersIcon } from "@/components/icons";
import { Alert, RetryButton, Skeleton } from "@/components/ui";
import { api, getApiError } from "@/lib/api";
import type { Result } from "@/lib/types";
import { breakdownRows, cn, formatDate, getGrade, isCorrect, studentClass, studentName, studentRoll } from "@/lib/utils";

import { EditResultDialog } from "@/components/edit-result-dialog";

export default function ResultDetailPage() {
  const params = useParams<{ id: string }>();
  const resultId = params.id;
  const [result, setResult] = useState<Result | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [isEditDialogOpen, setIsEditDialogOpen] = useState(false);

  const loadResult = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setResult(await api.getResult(resultId));
    } catch (caught) {
      setError(getApiError(caught, "The result could not be loaded."));
    } finally {
      setLoading(false);
    }
  }, [resultId]);

  useEffect(() => {
    void loadResult();
  }, [loadResult]);

  const handleSaveEdit = async (data: { name: string | null; roll_number: string | null; class_name: string | null }) => {
    await api.updateResult(resultId, data);
    // Reload result to show updated data
    await loadResult();
  };

  const rows = useMemo(() => result ? breakdownRows(result).sort((a, b) => Number(a.question) - Number(b.question)) : [], [result]);

  if (loading) {
    return <div className="space-y-6"><Skeleton className="h-20" /><Skeleton className="h-72" /><Skeleton className="h-96" /></div>;
  }

  if (!result) {
    return <div className="surface-card flex min-h-[420px] flex-col items-center justify-center p-8 text-center"><span className="grid h-14 w-14 place-items-center rounded-2xl bg-rose-50 text-rose-600"><FileIcon /></span><h1 className="mt-5 text-xl font-black">Result unavailable</h1><p className="mt-2 max-w-md text-sm leading-6 text-slate-500">{error || "This saved result may have been removed."}</p><RetryButton onClick={() => void loadResult()} /><Link className="button-ghost mt-2" href="/dashboard">Return to dashboard</Link></div>;
  }

  const passed = result.percentage >= 60;
  const statusTone = passed
    ? "bg-emerald-400/15 text-emerald-200"
    : result.percentage >= 40
      ? "bg-amber-400/15 text-amber-200"
      : "bg-rose-400/15 text-rose-200";
  const examName = result.exam?.name || "Exam result";

  return (
    <div className="animate-fade-in space-y-7">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <Link className="button-ghost -ml-3" href={`/exams/${result.exam_id}/results`}><ArrowLeftIcon size={17} /> Back to all results</Link>
        <span className="text-xs font-semibold text-slate-400">Result ID: {result.id}</span>
      </div>
      {error && <Alert>{error}</Alert>}

      <section className="surface-card overflow-hidden">
        <div className="relative overflow-hidden bg-[#15203a] p-6 text-white sm:p-8">
          <div className="absolute -right-16 -top-24 h-64 w-64 rounded-full bg-brand-500/25 blur-3xl" aria-hidden="true" />
          <div className="relative flex flex-col gap-7 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <div className="flex items-center gap-3">
                <p className="text-xs font-extrabold uppercase tracking-[0.17em] text-brand-200">Individual result</p>
                <button 
                  className="rounded bg-white/10 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white transition hover:bg-white/20"
                  onClick={() => setIsEditDialogOpen(true)}
                  type="button"
                >
                  Edit Details
                </button>
              </div>
              <h1 className="mt-3 text-2xl font-black tracking-tight sm:text-3xl">{studentName(result)}</h1>
              <p className="mt-2 text-sm text-slate-300">{examName}{result.exam?.subject ? ` · ${result.exam.subject}` : ""}</p>
              <div className="mt-5 flex flex-wrap gap-2"><span className="rounded-full bg-white/10 px-3 py-1.5 text-xs font-bold text-slate-200">Roll {studentRoll(result)}</span><span className="rounded-full bg-white/10 px-3 py-1.5 text-xs font-bold text-slate-200">Class {studentClass(result)}</span><span className={cn("rounded-full px-3 py-1.5 text-xs font-extrabold", statusTone)}>{passed ? "Passed" : "Failed"}</span></div>
            </div>
            <div className="flex items-center gap-5 rounded-2xl border border-white/10 bg-white/[0.07] p-5 backdrop-blur">
              <div className="grid h-20 w-20 place-items-center rounded-full border-[7px] border-brand-300/30 bg-white/5"><span className="text-2xl font-black">{getGrade(result.percentage)}</span></div>
              <div><p className="text-xs font-bold uppercase tracking-wider text-slate-400">Final score</p><p className="mt-1 text-3xl font-black">{result.score}<span className="text-base text-slate-400">/{result.total}</span></p><p className="mt-1 text-sm font-extrabold text-brand-200">{Number(result.percentage).toFixed(1)}%</p></div>
            </div>
          </div>
        </div>
        <div className="grid divide-y divide-slate-100 sm:grid-cols-2 sm:divide-x sm:divide-y-0 lg:grid-cols-4">
          {[
            { icon: <UsersIcon size={18} />, label: "Student", value: studentName(result) },
            { icon: <ExamIcon size={18} />, label: "Assessment", value: examName },
            { icon: <CalendarIcon size={18} />, label: "Scanned", value: formatDate(result.scanned_at, true) },
            { icon: <FileIcon size={18} />, label: "Source", value: result.filename || result.source_file || "Scanned sheet" },
          ].map((item) => <div className="flex min-w-0 items-center gap-3 p-5" key={item.label}><span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-slate-100 text-slate-500">{item.icon}</span><div className="min-w-0"><p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">{item.label}</p><p className="mt-1 truncate text-sm font-extrabold text-slate-800">{item.value}</p></div></div>)}
        </div>
      </section>

      <section className="surface-card overflow-hidden">
        <div className="flex flex-col gap-2 border-b border-slate-200 px-5 py-5 sm:flex-row sm:items-end sm:justify-between sm:px-7"><div><h2 className="text-lg font-black text-slate-950">Question breakdown</h2><p className="mt-1 text-sm text-slate-500">Compare each detected response with the saved answer key.</p></div><p className="text-xs font-bold text-slate-400">{result.score} correct · {Math.max(result.total - result.score, 0)} incorrect</p></div>
        {rows.length === 0 ? (
          <div className="p-10 text-center"><p className="font-extrabold text-slate-800">No question-level data is available</p><p className="mt-2 text-sm text-slate-500">The total score was saved, but this scan did not include a breakdown.</p></div>
        ) : (
          <>
            <div className="hidden overflow-x-auto sm:block">
              <table className="min-w-full divide-y divide-slate-200">
                <thead className="bg-slate-50"><tr>{["Question", "Detected answer", "Correct answer", "Result"].map((heading) => <th className={cn("px-7 py-3 text-[11px] font-extrabold uppercase tracking-[0.12em] text-slate-500", heading === "Question" ? "text-left" : "text-center")} key={heading} scope="col">{heading}</th>)}</tr></thead>
                <tbody className="divide-y divide-slate-100">{rows.map((row, index) => {
                  const correct = isCorrect(row);
                  const selected = row.student ?? row.selected_answer ?? "—";
                  const expected = row.correct ?? row.correct_answer ?? "—";
                  return <tr className="hover:bg-slate-50/70" key={`${row.question}-${index}`}><td className="px-7 py-4 text-sm font-black text-slate-800">Question {row.question}</td><td className="px-7 py-4 text-center"><span className={cn("inline-grid h-9 min-w-9 place-items-center rounded-lg px-2 text-sm font-black", correct ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700")}>{selected}</span></td><td className="px-7 py-4 text-center text-sm font-black text-slate-700">{expected}</td><td className="px-7 py-4 text-center"><span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-extrabold ring-1 ring-inset", correct ? "bg-emerald-50 text-emerald-700 ring-emerald-600/20" : "bg-rose-50 text-rose-700 ring-rose-600/20")}>{correct && <CheckIcon size={13} />}{correct ? "Correct" : selected === "—" ? "Unanswered" : "Incorrect"}</span></td></tr>;
                })}</tbody>
              </table>
            </div>
            <div className="grid grid-cols-2 gap-3 p-4 sm:hidden">{rows.map((row, index) => {
              const correct = isCorrect(row);
              const selected = row.student ?? row.selected_answer ?? "—";
              const expected = row.correct ?? row.correct_answer ?? "—";
              return <div className={cn("rounded-xl border p-3", correct ? "border-emerald-200 bg-emerald-50" : "border-rose-200 bg-rose-50")} key={`${row.question}-${index}`}><div className="flex items-center justify-between"><span className="text-xs font-extrabold text-slate-500">Q{row.question}</span><span className={cn("text-base font-black", correct ? "text-emerald-700" : "text-rose-700")}>{selected}</span></div><p className="mt-2 text-[11px] text-slate-500">Correct answer: <strong>{expected}</strong></p></div>;
            })}</div>
          </>
        )}
      </section>

      <EditResultDialog
        isOpen={isEditDialogOpen}
        onClose={() => setIsEditDialogOpen(false)}
        onSave={handleSaveEdit}
        result={result}
      />
    </div>
  );
}
