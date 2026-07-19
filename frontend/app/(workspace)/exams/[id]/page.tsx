"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { CalendarIcon, ChartIcon, ChevronRightIcon, ExamIcon, KeyIcon, ScanIcon } from "@/components/icons";
import { ScanResultCard } from "@/components/scan-result-card";
import { SheetUploader } from "@/components/sheet-uploader";
import { Alert, PageTitle, RetryButton, Skeleton } from "@/components/ui";
import { api, getApiError } from "@/lib/api";
import type { AnswerMap, Exam, ScanBatchPayload } from "@/lib/types";
import { cn, formatDate, normalizeAnswerMap } from "@/lib/utils";

export default function ExamDetailPage() {
  const params = useParams<{ id: string }>();
  const examId = params.id;
  const [exam, setExam] = useState<Exam | null>(null);
  const [answerKey, setAnswerKey] = useState<AnswerMap>({});
  const [savedResultCount, setSavedResultCount] = useState(0);
  const [batch, setBatch] = useState<ScanBatchPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadExam = useCallback(async () => {
    setLoading(true);
    setError("");
    const [examResponse, keyResponse, resultsResponse] = await Promise.allSettled([
      api.getExam(examId),
      api.getAnswerKey(examId),
      api.getResults(examId),
    ]);
    if (examResponse.status === "fulfilled") setExam(examResponse.value);
    else setError(getApiError(examResponse.reason, "This exam could not be loaded."));
    setAnswerKey(keyResponse.status === "fulfilled" ? normalizeAnswerMap(keyResponse.value) : {});
    setSavedResultCount(resultsResponse.status === "fulfilled" ? resultsResponse.value.results.length : 0);
    setLoading(false);
  }, [examId]);

  useEffect(() => {
    void loadExam();
  }, [loadExam]);

  const keyEntries = useMemo(
    () => Object.entries(answerKey).sort(([a], [b]) => Number(a) - Number(b)),
    [answerKey],
  );
  const hasAnswerKey = exam ? keyEntries.length === exam.total_questions : keyEntries.length > 0;

  function handleComplete(payload: ScanBatchPayload) {
    setBatch(payload);
    setSavedResultCount((count) => count + payload.results.length);
    window.setTimeout(() => document.getElementById("latest-results")?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
  }

  if (loading) {
    return <div className="space-y-6"><Skeleton className="h-28" /><div className="grid gap-5 lg:grid-cols-3"><Skeleton className="h-40 lg:col-span-2" /><Skeleton className="h-40" /></div><Skeleton className="h-[440px]" /></div>;
  }

  if (!exam) {
    return <div className="surface-card flex min-h-[420px] flex-col items-center justify-center p-8 text-center"><span className="grid h-14 w-14 place-items-center rounded-2xl bg-rose-50 text-rose-600"><ExamIcon size={26} /></span><h1 className="mt-5 text-xl font-black">Exam unavailable</h1><p className="mt-2 max-w-md text-sm leading-6 text-slate-500">{error || "The exam may have been deleted or you may not have access."}</p><RetryButton onClick={() => void loadExam()} /><Link className="button-ghost mt-2" href="/dashboard">Return to dashboard</Link></div>;
  }

  return (
    <div className="animate-fade-in space-y-7">
      <PageTitle
        eyebrow={exam.subject || "Exam workspace"}
        title={exam.name}
        description="Upload student sheets, review each scan, and move into the full results view when you’re ready."
        actions={<Link className="button-secondary" href={`/exams/${exam.id}/results`}><ChartIcon size={18} /> View all results <ChevronRightIcon size={16} /></Link>}
      />
      {error && <Alert>{error}</Alert>}

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="Exam information">
        {[
          { label: "Questions", value: exam.total_questions, detail: `${exam.options_per_question} options each`, icon: <ExamIcon /> },
          { label: "Answer key", value: `${keyEntries.length}/${exam.total_questions}`, detail: hasAnswerKey ? "Ready to grade" : "Setup incomplete", icon: <KeyIcon /> },
          { label: "Saved scans", value: savedResultCount, detail: "Student results", icon: <ScanIcon /> },
          { label: "Created", value: formatDate(exam.created_at), detail: exam.subject || "General", icon: <CalendarIcon /> },
        ].map((item) => (
          <div className="surface-card p-4" key={item.label}><div className="flex items-center gap-3"><span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-brand-50 text-brand-600">{item.icon}</span><div className="min-w-0"><p className="text-xs font-semibold text-slate-500">{item.label}</p><p className="mt-0.5 truncate text-base font-black text-slate-950">{item.value}</p><p className="truncate text-[11px] text-slate-400">{item.detail}</p></div></div></div>
        ))}
      </section>

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_330px]">
        <SheetUploader examId={exam.id} hasAnswerKey={hasAnswerKey} onComplete={handleComplete} />

        <aside className="surface-card overflow-hidden xl:sticky xl:top-6">
          <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4"><div><h2 className="font-black text-slate-950">Answer key</h2><p className="mt-0.5 text-xs text-slate-500">{keyEntries.length} saved answers</p></div><span className={cn("rounded-full px-2.5 py-1 text-[11px] font-extrabold", hasAnswerKey ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700")}>{hasAnswerKey ? "Complete" : "Incomplete"}</span></div>
          {keyEntries.length > 0 ? (
            <div className="max-h-[410px] overflow-y-auto p-4"><div className="grid grid-cols-4 gap-2">{keyEntries.map(([question, answer]) => <div className="rounded-lg border border-slate-200 bg-slate-50 px-2 py-2 text-center" key={question}><p className="text-[10px] font-bold text-slate-400">Q{question}</p><p className="mt-0.5 text-sm font-black text-brand-700">{answer}</p></div>)}</div></div>
          ) : (
            <div className="px-5 py-10 text-center"><span className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-amber-50 text-amber-600"><KeyIcon /></span><h3 className="mt-4 text-sm font-extrabold">No key saved yet</h3><p className="mt-2 text-xs leading-5 text-slate-500">Add the correct answers before scanning student sheets.</p></div>
          )}
          <div className="border-t border-slate-200 p-4"><Link className="button-secondary w-full" href={`/exams/create?exam=${encodeURIComponent(exam.id)}&step=answer-key`}><KeyIcon size={17} /> {keyEntries.length ? "Replace answer key" : "Add answer key"}</Link></div>
        </aside>
      </div>

      {batch && (
        <section className="scroll-mt-8" id="latest-results">
          <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between"><div><p className="text-xs font-extrabold uppercase tracking-[0.16em] text-emerald-600">Batch complete</p><h2 className="mt-1 text-xl font-black tracking-tight text-slate-950">Latest scan results</h2><p className="mt-1 text-sm text-slate-500">{batch.results.length} saved · {batch.errors?.length || batch.failed_count || 0} could not be processed</p></div><Link className="button-secondary" href={`/exams/${exam.id}/results`}>Open analytics <ChevronRightIcon size={16} /></Link></div>
          {batch.errors && batch.errors.length > 0 && <div className="mb-4"><Alert title="Some sheets need attention">{batch.errors.map((failure) => `${failure.filename}: ${failure.message}`).join(" · ")}</Alert></div>}
          {batch.results.length > 0 ? <div className="space-y-4">{batch.results.map((result) => <ScanResultCard key={result.id} result={result} />)}</div> : <Alert title="No sheets were graded">Review the processing errors above, then try those files again.</Alert>}
        </section>
      )}
    </div>
  );
}
