"use client";

import { Suspense, useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { AnswerKeySetup } from "@/components/answer-key-setup";
import { ArrowLeftIcon, ArrowRightIcon, CheckIcon, ExamIcon, KeyIcon } from "@/components/icons";
import { Alert, PageTitle, Skeleton, Spinner } from "@/components/ui";
import { api, getApiError } from "@/lib/api";
import type { AnswerMap, CreateExamInput, Exam } from "@/lib/types";
import { cn, normalizeAnswerMap } from "@/lib/utils";

const initialForm: CreateExamInput = {
  name: "",
  subject: "",
  total_questions: 20,
  options_per_question: 4,
};

function Stepper({ answerKeyStep }: { answerKeyStep: boolean }) {
  return (
    <ol className="surface-card grid grid-cols-2 p-2" aria-label="Create exam progress">
      {[
        { label: "Exam details", icon: ExamIcon, complete: answerKeyStep },
        { label: "Answer key", icon: KeyIcon, complete: false },
      ].map((step, index) => {
        const active = answerKeyStep ? index === 1 : index === 0;
        const Icon = step.icon;
        return (
          <li aria-current={active ? "step" : undefined} className={cn("flex items-center gap-3 rounded-xl px-3 py-3 text-sm font-bold sm:px-5", active ? "bg-brand-50 text-brand-700" : step.complete ? "text-emerald-700" : "text-slate-400")} key={step.label}>
            <span className={cn("grid h-8 w-8 place-items-center rounded-full", active ? "bg-brand-600 text-white" : step.complete ? "bg-emerald-100 text-emerald-700" : "bg-slate-100")}>{step.complete ? <CheckIcon size={16} /> : <Icon size={16} />}</span>
            <span className="hidden sm:inline">{index + 1}. {step.label}</span><span className="sm:hidden">{step.label}</span>
          </li>
        );
      })}
    </ol>
  );
}

function CreateExamContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const examId = searchParams.get("exam");
  const [form, setForm] = useState<CreateExamInput>(initialForm);
  const [exam, setExam] = useState<Exam | null>(null);
  const [existingAnswers, setExistingAnswers] = useState<AnswerMap>({});
  const [loadingExam, setLoadingExam] = useState(Boolean(examId));
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!examId) { setLoadingExam(false); return; }
    let active = true;
    setLoadingExam(true);
    void Promise.allSettled([api.getExam(examId), api.getAnswerKey(examId)]).then(([examResponse, keyResponse]) => {
      if (!active) return;
      if (examResponse.status === "fulfilled") setExam(examResponse.value);
      else setError(getApiError(examResponse.reason, "The exam could not be loaded."));
      if (keyResponse.status === "fulfilled") setExistingAnswers(normalizeAnswerMap(keyResponse.value));
    }).finally(() => {
      if (active) setLoadingExam(false);
    });
    return () => { active = false; };
  }, [examId]);

  function update<K extends keyof CreateExamInput>(key: K, value: CreateExamInput[K]) {
    setForm((current) => ({ ...current, [key]: value }));
    setError("");
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const name = form.name.trim();
    const subject = form.subject?.trim();
    if (name.length < 3) { setError("Exam name must be at least 3 characters."); return; }
    if (form.total_questions < 10 || form.total_questions > 100) { setError("Total questions must be between 10 and 100."); return; }
    setSubmitting(true);
    try {
      const created = await api.createExam({ ...form, name, subject });
      setExam(created);
      router.replace(`/exams/create?exam=${encodeURIComponent(created.id)}&step=answer-key`);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (caught) {
      setError(getApiError(caught, "The exam could not be created."));
    } finally {
      setSubmitting(false);
    }
  }

  const answerKeyStep = Boolean(exam || examId);

  return (
    <div className="animate-fade-in space-y-7">
      <div><Link className="button-ghost -ml-3 mb-3" href="/dashboard"><ArrowLeftIcon size={17} /> Back to dashboard</Link><PageTitle eyebrow="Assessment setup" title={answerKeyStep ? "Add the answer key" : "Create a new exam"} description={answerKeyStep ? `Finish setting up “${exam?.name || "your exam"}” so sheets can be graded.` : "Start with the basics. You’ll add the correct answers in the next step."} /></div>
      <Stepper answerKeyStep={answerKeyStep} />
      {error && <Alert>{error}</Alert>}

      {loadingExam ? (
        <div className="space-y-4"><Skeleton className="h-24" /><Skeleton className="h-[420px]" /></div>
      ) : answerKeyStep && exam ? (
        <AnswerKeySetup exam={exam} initialAnswers={existingAnswers} />
      ) : answerKeyStep ? (
        <div className="surface-card p-8 text-center"><h2 className="text-lg font-black">Exam unavailable</h2><p className="mt-2 text-sm text-slate-500">Return to the dashboard and open the exam again.</p><Link className="button-secondary mt-5" href="/dashboard">View dashboard</Link></div>
      ) : (
        <form className="surface-card overflow-hidden" onSubmit={handleSubmit}>
          <div className="border-b border-slate-200 px-5 py-5 sm:px-7"><div className="flex items-start gap-3"><span className="grid h-11 w-11 place-items-center rounded-xl bg-brand-50 text-brand-600"><ExamIcon /></span><div><h2 className="text-lg font-black text-slate-950">Exam details</h2><p className="mt-1 text-sm leading-6 text-slate-500">These details appear throughout the workspace and exports.</p></div></div></div>
          <div className="grid gap-6 p-5 sm:p-7 lg:grid-cols-2">
            <div className="lg:col-span-2">
              <label className="field-label" htmlFor="exam-name">Exam name <span className="text-rose-500">*</span></label>
              <input autoFocus className="text-field" id="exam-name" maxLength={255} minLength={3} onChange={(event) => update("name", event.target.value)} placeholder="e.g. Biology Midterm — Section 10B" required value={form.name} />
              <p className="mt-2 text-xs text-slate-400">Use a name teachers can recognize at a glance.</p>
            </div>
            <div>
              <label className="field-label" htmlFor="subject">Subject</label>
              <input className="text-field" id="subject" maxLength={100} onChange={(event) => update("subject", event.target.value)} placeholder="e.g. Biology" value={form.subject} />
            </div>
            <div>
              <label className="field-label" htmlFor="question-count">Total questions <span className="text-rose-500">*</span></label>
              <input className="text-field" id="question-count" max={100} min={10} onChange={(event) => update("total_questions", Number(event.target.value))} required type="number" value={form.total_questions} />
              <p className="mt-2 text-xs text-slate-400">Between 10 and 100 questions.</p>
            </div>
            <fieldset className="lg:col-span-2">
              <legend className="field-label">Options per question</legend>
              <div className="grid gap-3 sm:grid-cols-2">
                {([4, 5] as const).map((count) => {
                  const selected = form.options_per_question === count;
                  return (
                    <label className={cn("flex cursor-pointer items-center justify-between rounded-xl border p-4 transition", selected ? "border-brand-500 bg-brand-50 ring-2 ring-brand-100" : "border-slate-300 bg-white hover:border-slate-400")} key={count}>
                      <span><span className="block text-sm font-extrabold text-slate-900">{count} options</span><span className="mt-1 block text-xs text-slate-500">Answers A through {count === 4 ? "D" : "E"}</span></span>
                      <span className={cn("grid h-5 w-5 place-items-center rounded-full border", selected ? "border-brand-600 bg-brand-600 text-white" : "border-slate-300")}>{selected && <CheckIcon size={13} />}</span>
                      <input checked={selected} className="sr-only" name="options" onChange={() => update("options_per_question", count)} type="radio" value={count} />
                    </label>
                  );
                })}
              </div>
            </fieldset>
          </div>
          <div className="flex flex-col-reverse gap-3 border-t border-slate-200 bg-slate-50/60 px-5 py-4 sm:flex-row sm:items-center sm:justify-end sm:px-7">
            <Link className="button-secondary" href="/dashboard">Cancel</Link>
            <button className="button-primary min-w-44" disabled={submitting} type="submit">{submitting ? <><Spinner /> Creating exam…</> : <>Continue to answer key <ArrowRightIcon size={17} /></>}</button>
          </div>
        </form>
      )}
    </div>
  );
}

export default function CreateExamPage() {
  return <Suspense fallback={<div className="space-y-5"><Skeleton className="h-24" /><Skeleton className="h-20" /><Skeleton className="h-[480px]" /></div>}><CreateExamContent /></Suspense>;
}
