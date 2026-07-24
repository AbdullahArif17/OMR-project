"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { CloseIcon, KeyIcon } from "@/components/icons";
import { Alert, Spinner } from "@/components/ui";
import type { Result } from "@/lib/types";
import { cn } from "@/lib/utils";

interface EditResultDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (data: {
    name: string | null;
    roll_number: string | null;
    class_name: string | null;
    answers?: Record<number, string> | null;
  }) => Promise<void>;
  result: Result;
}

function extractAnswersFromBreakdown(
  result: Result,
): Record<number, { student: string | null; correct: string | null; isCorrect: boolean }> {
  const raw = result.breakdown;
  if (!raw) return {};

  const entries: Record<number, { student: string | null; correct: string | null; isCorrect: boolean }> = {};

  if (Array.isArray(raw)) {
    raw.forEach((item, index) => {
      const q = item.question ?? index + 1;
      const correct = item.correct ?? item.correct_answer ?? null;
      const student = item.student ?? item.selected_answer ?? null;
      entries[Number(q)] = {
        student: student ? String(student).toUpperCase() : null,
        correct: correct ? String(correct).toUpperCase() : null,
        isCorrect: item.result === true || item.is_correct === true,
      };
    });
  } else {
    Object.entries(raw).forEach(([question, item]) => {
      const qNum = Number(question);
      if (Number.isNaN(qNum)) return;
      const rawItem = item as Record<string, unknown>;
      const correct = (rawItem.correct ?? rawItem.correct_answer) as string | null;
      const student = (rawItem.student ?? rawItem.selected_answer) as string | null;
      entries[qNum] = {
        student: student ? String(student).toUpperCase() : null,
        correct: correct ? String(correct).toUpperCase() : null,
        isCorrect: rawItem.result === true || rawItem.is_correct === true,
      };
    });
  }

  return entries;
}

export function EditResultDialog({ isOpen, onClose, onSave, result }: EditResultDialogProps) {
  const [name, setName] = useState(result.student?.name || result.student_name || "");
  const [rollNumber, setRollNumber] = useState(result.student?.roll_number || result.roll_number || "");
  const [className, setClassName] = useState(result.student?.class_name || result.class_name || "");
  const [overriddenAnswers, setOverriddenAnswers] = useState<Record<number, string>>({});
  const [showAnswerEditor, setShowAnswerEditor] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const optionsPerQuestion = result.exam?.options_per_question || 4;
  const totalQuestions = result.total;
  const validOptions = useMemo(() => "ABCDE".slice(0, optionsPerQuestion).split(""), [optionsPerQuestion]);

  const breakdownData = useMemo(() => extractAnswersFromBreakdown(result), [result]);

  const changesExist = useMemo(() => {
    for (const [q, a] of Object.entries(overriddenAnswers)) {
      const orig = breakdownData[Number(q)]?.student;
      if (a !== orig) return true;
    }
    return false;
  }, [overriddenAnswers, breakdownData]);

  useEffect(() => {
    if (isOpen) {
      setName(result.student?.name || result.student_name || "");
      setRollNumber(result.student?.roll_number || result.roll_number || "");
      setClassName(result.student?.class_name || result.class_name || "");
      setError("");
      setShowAnswerEditor(false);

      const answers = extractAnswersFromBreakdown(result);
      setOverriddenAnswers(
        Object.fromEntries(
          Object.entries(answers)
            .filter(([, v]) => v.student !== null)
            .map(([q, v]) => [q, v.student!]),
        ),
      );
    }
  }, [isOpen, result]);

  if (!isOpen) return null;

  function updateAnswer(question: number, answer: string) {
    setOverriddenAnswers((prev) => ({ ...prev, [question]: answer }));
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError("");

    try {
      await onSave({
        name: name.trim() || null,
        roll_number: rollNumber.trim() || null,
        class_name: className.trim() || null,
        answers: showAnswerEditor && changesExist ? overriddenAnswers : null,
      });
      onClose();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to update result.");
    } finally {
      setSaving(false);
    }
  }

  const changedQuestionCount = Object.entries(overriddenAnswers).filter(
    ([q, a]) => a !== breakdownData[Number(q)]?.student,
  ).length;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-sm" role="dialog" aria-modal="true">
      <div className="animate-in fade-in zoom-in-95 surface-card flex max-h-[92vh] w-full max-w-2xl flex-col overflow-hidden">
        {/* Header */}
        <div className="flex shrink-0 items-center justify-between border-b border-slate-200 px-6 py-5">
          <h2 className="text-lg font-black text-slate-950">Edit Result</h2>
          <button className="rounded-full p-1 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600" onClick={onClose} type="button">
            <span className="sr-only">Close dialog</span>
            <CloseIcon size={20} />
          </button>
        </div>

        {/* Scrollable body */}
        <form className="flex-1 overflow-y-auto" onSubmit={handleSubmit}>
          <div className="space-y-6 px-6 py-5">
            {error && <Alert>{error}</Alert>}

            {/* Student metadata */}
            <div>
              <p className="mb-4 text-xs font-extrabold uppercase tracking-[0.16em] text-slate-400">Student information</p>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="sm:col-span-2">
                  <label className="field-label" htmlFor="edit-name">Student Name</label>
                  <input className="text-field" id="edit-name" onChange={(e) => setName(e.target.value)} placeholder="e.g. John Doe" value={name} />
                </div>
                <div>
                  <label className="field-label" htmlFor="edit-roll">Roll Number</label>
                  <input className="text-field" id="edit-roll" onChange={(e) => setRollNumber(e.target.value)} placeholder="e.g. 12345" value={rollNumber} />
                </div>
                <div>
                  <label className="field-label" htmlFor="edit-class">Class</label>
                  <input className="text-field" id="edit-class" onChange={(e) => setClassName(e.target.value)} placeholder="e.g. 10th Grade" value={className} />
                </div>
              </div>
            </div>

            {/* Answer override toggle */}
            <div>
              <div className="flex items-center justify-between">
                <p className="text-xs font-extrabold uppercase tracking-[0.16em] text-slate-400">Answer overrides</p>
                <button
                  className="rounded-full border border-brand-200 bg-brand-50 px-3 py-1 text-[11px] font-extrabold text-brand-700 transition hover:bg-brand-100"
                  onClick={() => setShowAnswerEditor((prev) => !prev)}
                  type="button"
                >
                  <KeyIcon className="mr-1 inline-block" size={13} />
                  {showAnswerEditor ? "Hide answer editor" : "Edit answers"}
                </button>
              </div>
              {showAnswerEditor && (
                <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50/70 p-4">
                  <p className="mb-3 text-xs text-slate-500">Select new answers to override the auto-detected marks. The score will be recalculated.</p>
                  <div className="grid max-h-[320px] grid-cols-2 gap-x-6 gap-y-1 overflow-y-auto pr-2 sm:grid-cols-3 lg:grid-cols-4">
                    {Array.from({ length: totalQuestions }, (_, i) => i + 1).map((question) => {
                      const data = breakdownData[question];
                      const currentAnswer = overriddenAnswers[question] ?? data?.student ?? "—";
                      const correctAnswer = data?.correct ?? "—";
                      const isCorrect = data?.isCorrect ?? false;
                      return (
                        <div className="flex items-center gap-2 py-1" key={question}>
                          <span className={cn(
                            "min-w-[32px] text-[11px] font-extrabold tabular-nums",
                            isCorrect ? "text-emerald-600" : "text-rose-600",
                          )}>
                            {question}
                          </span>
                          <select
                            className="w-12 rounded-lg border border-slate-200 bg-white px-1 py-1.5 text-center text-xs font-bold text-slate-800 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                            onChange={(e) => updateAnswer(question, e.target.value)}
                            value={currentAnswer}
                          >
                            {validOptions.map((option) => (
                              <option key={option} value={option}>{option}</option>
                            ))}
                          </select>
                          {correctAnswer !== "—" && (
                            <span className="text-[10px] font-semibold text-slate-400">
                              key: {correctAnswer}
                            </span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                  {changedQuestionCount > 0 && (
                    <p className="mt-3 rounded-lg bg-brand-50 px-3 py-2 text-[11px] font-extrabold text-brand-700">
                      {changedQuestionCount} answer{changedQuestionCount !== 1 ? "s" : ""} will be overridden and the score recalculated
                    </p>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Footer */}
          <div className="flex shrink-0 items-center justify-end gap-3 border-t border-slate-200 bg-slate-50/60 px-6 py-4">
            <button className="button-secondary" disabled={saving} onClick={onClose} type="button">Cancel</button>
            <button className="button-primary min-w-36" disabled={saving} type="submit">
              {saving ? <><Spinner /> Saving…</> : "Save Changes"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
