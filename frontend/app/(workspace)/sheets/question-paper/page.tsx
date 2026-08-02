"use client";

import { useRef, useState, useEffect } from "react";
import Link from "next/link";
import { ArrowLeftIcon, CheckIcon, PlusIcon, TrashIcon } from "@/components/icons";
import { Alert, PageTitle, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

interface QuestionItem {
  id: number;
  text: string;
  options: string[];
}

const OPTION_LABELS = ["A", "B", "C", "D", "E"];

let nextId = 1;
function makeQuestion(optionCount: number): QuestionItem {
  return {
    id: nextId++,
    text: "",
    options: Array.from({ length: optionCount }, () => ""),
  };
}

export default function QuestionPaperPage() {
  const [title, setTitle] = useState("Biology Midterm Examination");
  const [subject, setSubject] = useState("Biology");
  const [instructions, setInstructions] = useState(
    "• Read each question carefully before answering.\n• Fill in the circle completely for your chosen answer.\n• Use a dark pencil or pen — do not use erasable ink.\n• Each question carries equal marks."
  );
  const [duration, setDuration] = useState("60 minutes");
  const [totalMarks, setTotalMarks] = useState("");
  const [teacherName, setTeacherName] = useState("");
  const [optionsPerQuestion, setOptionsPerQuestion] = useState<4 | 5>(4);
  const [questions, setQuestions] = useState<QuestionItem[]>([
    makeQuestion(4),
    makeQuestion(4),
    makeQuestion(4),
  ]);
  const [includeName, setIncludeName] = useState(true);
  const [includeRoll, setIncludeRoll] = useState(true);
  const [error, setError] = useState("");
  
  const [printing, setPrinting] = useState(false);
  const [omrImageUrl, setOmrImageUrl] = useState<string | null>(null);

  const printRef = useRef<HTMLDivElement>(null);

  // Clean up object URL when component unmounts or image changes
  useEffect(() => {
    return () => {
      if (omrImageUrl) URL.revokeObjectURL(omrImageUrl);
    };
  }, [omrImageUrl]);

  function addQuestion() {
    if (questions.length >= 100) {
      setError("Maximum 100 questions allowed.");
      return;
    }
    setQuestions((prev) => [...prev, makeQuestion(optionsPerQuestion)]);
  }

  function removeQuestion(id: number) {
    setQuestions((prev) => prev.filter((q) => q.id !== id));
  }

  function updateQuestionText(id: number, text: string) {
    setQuestions((prev) =>
      prev.map((q) => (q.id === id ? { ...q, text } : q))
    );
  }

  function updateOption(questionId: number, optionIndex: number, value: string) {
    setQuestions((prev) =>
      prev.map((q) =>
        q.id === questionId
          ? { ...q, options: q.options.map((o, i) => (i === optionIndex ? value : o)) }
          : q
      )
    );
  }

  function handleOptionsCountChange(count: 4 | 5) {
    setOptionsPerQuestion(count);
    setQuestions((prev) =>
      prev.map((q) => {
        if (q.options.length === count) return q;
        if (count > q.options.length) {
          return { ...q, options: [...q.options, ...Array.from({ length: count - q.options.length }, () => "")] };
        }
        return { ...q, options: q.options.slice(0, count) };
      })
    );
  }

  async function handlePrint() {
    const emptyQuestions = questions.filter((q) => !q.text.trim());
    if (emptyQuestions.length > 0) {
      setError(`${emptyQuestions.length} question(s) have no text. Please fill them in or remove them.`);
      return;
    }
    
    setError("");
    setPrinting(true);
    
    try {
      // 1. Fetch the perfect OMR bubble sheet from the backend
      const blob = await api.previewSheet({
        title: title.trim() || "EXAMINATION",
        totalQuestions: Math.max(10, questions.length),
        optionsPerQuestion,
        includeName,
        includeRoll,
      });
      
      const url = URL.createObjectURL(blob);
      setOmrImageUrl(url);
      
      // 2. Wait a moment for React to render the <img> tag and the browser to decode it
      setTimeout(() => {
        window.print();
        setPrinting(false);
      }, 500);
      
    } catch (err) {
      console.error(err);
      setError("Failed to generate the OMR sheet attachment. Please try again.");
      setPrinting(false);
    }
  }

  const filledCount = questions.filter((q) => q.text.trim()).length;

  return (
    <>
      {/* ─── Editor (hidden during print) ─── */}
      <div className="animate-fade-in space-y-7 print:hidden">
        <div>
          <Link className="button-ghost -ml-3 mb-3" href="/dashboard">
            <ArrowLeftIcon size={17} /> Back to dashboard
          </Link>
          <PageTitle
            eyebrow="Exam Paper Builder"
            title="Create Question Paper"
            description="Type your questions and answer options, then print a complete exam paper with the OMR sheet automatically attached at the end."
          />
        </div>

        {error && <Alert>{error}</Alert>}

        {/* Paper Settings */}
        <section className="surface-card overflow-hidden">
          <div className="border-b border-slate-200 px-5 py-5 sm:px-7">
            <h2 className="text-lg font-black text-slate-950">Paper Settings</h2>
            <p className="mt-1 text-sm text-slate-500">Configure the exam header that appears on the printed sheet.</p>
          </div>
          <div className="grid gap-5 p-5 sm:p-7 lg:grid-cols-2">
            <div className="lg:col-span-2">
              <label className="field-label" htmlFor="paper-title">Exam Title <span className="text-rose-500">*</span></label>
              <input className="text-field" id="paper-title" maxLength={120} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Biology Midterm Examination" required value={title} />
            </div>
            <div>
              <label className="field-label" htmlFor="paper-subject">Subject</label>
              <input className="text-field" id="paper-subject" maxLength={60} onChange={(e) => setSubject(e.target.value)} placeholder="e.g. Biology" value={subject} />
            </div>
            <div>
              <label className="field-label" htmlFor="paper-duration">Duration</label>
              <input className="text-field" id="paper-duration" maxLength={30} onChange={(e) => setDuration(e.target.value)} placeholder="e.g. 60 minutes" value={duration} />
            </div>
            <div>
              <label className="field-label" htmlFor="paper-total-marks">Total Marks (Optional)</label>
              <input className="text-field" id="paper-total-marks" maxLength={30} onChange={(e) => setTotalMarks(e.target.value)} placeholder={`e.g. ${questions.length}`} value={totalMarks} />
            </div>
            <div>
              <label className="field-label" htmlFor="paper-teacher-name">Teacher Name (Optional)</label>
              <input className="text-field" id="paper-teacher-name" maxLength={60} onChange={(e) => setTeacherName(e.target.value)} placeholder="e.g. Mr. Smith" value={teacherName} />
            </div>
            <div className="lg:col-span-2">
              <label className="field-label" htmlFor="paper-instructions">Instructions (one per line)</label>
              <textarea className="text-field min-h-[100px] resize-y" id="paper-instructions" onChange={(e) => setInstructions(e.target.value)} placeholder="Each line becomes a bullet point" rows={4} value={instructions} />
            </div>

            <fieldset>
              <legend className="field-label">Options per question</legend>
              <div className="grid gap-3 sm:grid-cols-2">
                {([4, 5] as const).map((count) => {
                  const selected = optionsPerQuestion === count;
                  return (
                    <label className={cn("flex cursor-pointer items-center justify-between rounded-xl border p-3 transition", selected ? "border-brand-500 bg-brand-50 ring-2 ring-brand-100" : "border-slate-300 bg-white hover:border-slate-400")} key={count}>
                      <span className="text-sm font-extrabold text-slate-900">{count} options (A–{OPTION_LABELS[count - 1]})</span>
                      <span className={cn("grid h-5 w-5 place-items-center rounded-full border", selected ? "border-brand-600 bg-brand-600 text-white" : "border-slate-300")}>{selected && <CheckIcon size={13} />}</span>
                      <input checked={selected} className="sr-only" name="optcount" onChange={() => handleOptionsCountChange(count)} type="radio" value={count} />
                    </label>
                  );
                })}
              </div>
            </fieldset>

            <fieldset className="mt-1">
              <legend className="field-label mb-3">Student Fields</legend>
              <div className="flex flex-col sm:flex-row gap-5">
                <label className="flex items-center gap-3 cursor-pointer">
                  <input checked={includeName} className="h-5 w-5 rounded border-slate-300 text-brand-600 focus:ring-brand-600" onChange={(e) => setIncludeName(e.target.checked)} type="checkbox" />
                  <span className="text-sm font-bold text-slate-700">Name field</span>
                </label>
                <label className="flex items-center gap-3 cursor-pointer">
                  <input checked={includeRoll} className="h-5 w-5 rounded border-slate-300 text-brand-600 focus:ring-brand-600" onChange={(e) => setIncludeRoll(e.target.checked)} type="checkbox" />
                  <span className="text-sm font-bold text-slate-700">Roll number field</span>
                </label>
              </div>
            </fieldset>
          </div>
        </section>

        {/* Questions Editor */}
        <section className="surface-card overflow-hidden">
          <div className="flex items-center justify-between border-b border-slate-200 px-5 py-5 sm:px-7">
            <div>
              <h2 className="text-lg font-black text-slate-950">Questions</h2>
              <p className="mt-1 text-sm text-slate-500">{filledCount} of {questions.length} questions filled in</p>
            </div>
            <button className="button-secondary" onClick={addQuestion} type="button">
              <PlusIcon size={16} /> Add Question
            </button>
          </div>

          <div className="divide-y divide-slate-100">
            {questions.map((question, index) => (
              <div className="px-5 py-5 sm:px-7" key={question.id}>
                <div className="flex items-start gap-3">
                  <span className="mt-2.5 grid h-8 w-8 shrink-0 place-items-center rounded-full bg-brand-50 text-xs font-black text-brand-700">
                    {index + 1}
                  </span>
                  <div className="flex-1 space-y-3">
                    <div className="flex items-start gap-2">
                      <textarea
                        className="text-field min-h-[44px] flex-1 resize-y"
                        onChange={(e) => updateQuestionText(question.id, e.target.value)}
                        placeholder={`Enter question ${index + 1}…`}
                        rows={1}
                        value={question.text}
                      />
                      <button
                        aria-label={`Remove question ${index + 1}`}
                        className="mt-1 rounded-lg p-2 text-slate-400 transition hover:bg-rose-50 hover:text-rose-600"
                        onClick={() => removeQuestion(question.id)}
                        type="button"
                      >
                        <TrashIcon size={16} />
                      </button>
                    </div>
                    <div className="grid gap-2 sm:grid-cols-2">
                      {question.options.map((option, optIdx) => (
                        <div className="flex items-center gap-2" key={optIdx}>
                          <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full border-2 border-slate-300 text-[11px] font-black text-slate-500">
                            {OPTION_LABELS[optIdx]}
                          </span>
                          <input
                            className="text-field flex-1 py-2 text-sm"
                            onChange={(e) => updateOption(question.id, optIdx, e.target.value)}
                            placeholder={`Option ${OPTION_LABELS[optIdx]}…`}
                            value={option}
                          />
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {questions.length === 0 && (
            <div className="px-5 py-12 text-center">
              <p className="font-extrabold text-slate-800">No questions added yet</p>
              <p className="mt-2 text-sm text-slate-500">Click &ldquo;Add Question&rdquo; to get started.</p>
            </div>
          )}

          <div className="flex gap-3 border-t border-slate-200 bg-slate-50/60 px-5 py-4 sm:items-center sm:justify-between sm:px-7">
            <button className="button-secondary" onClick={addQuestion} type="button">
              <PlusIcon size={16} /> Add Question
            </button>
            <button
              className="button-primary min-w-44"
              disabled={questions.length === 0 || printing}
              onClick={() => void handlePrint()}
              type="button"
            >
              {printing ? <><Spinner /> Preparing document…</> : "Print Question Paper"}
            </button>
          </div>
        </section>
      </div>

      {/* ─── Printable Paper (visible only during print) ─── */}
      {/* We only render this section into the DOM when generating/printing to keep it perfectly clean */}
      {(printing || omrImageUrl) && (
        <div className="hidden print:block" ref={printRef}>
          <style jsx>{`
            @media print {
              @page {
                size: A4;
                margin: 18mm 15mm 15mm 15mm;
              }
              body {
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
              }
              .omr-sheet-page {
                page-break-before: always;
                margin: 0;
                padding: 0;
              }
              .omr-sheet-image {
                width: 100%;
                height: 100%;
                object-fit: contain;
              }
            }
          `}</style>

          {/* PAGE 1..N: QUESTIONS */}
          <div>
            {/* Header */}
            <div style={{ borderBottom: "2px solid #000", paddingBottom: "10px", marginBottom: "14px" }}>
              <h1 style={{ fontSize: "20px", fontWeight: 900, textAlign: "center", textTransform: "uppercase", letterSpacing: "0.05em", margin: 0 }}>
                {title || "EXAMINATION"}
              </h1>
              {(subject || duration || teacherName || totalMarks) && (
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px", marginTop: "6px", color: "#333" }}>
                  {subject && <span><strong>Subject:</strong> {subject}</span>}
                  {teacherName && <span><strong>Teacher:</strong> {teacherName}</span>}
                  {duration && <span><strong>Time Allowed:</strong> {duration}</span>}
                  <span><strong>Total Marks:</strong> {totalMarks || questions.length}</span>
                </div>
              )}
            </div>

            {/* Instructions */}
            {instructions.trim() && (
              <div style={{ border: "1px solid #ccc", borderRadius: "4px", padding: "8px 12px", marginBottom: "16px", fontSize: "10px", color: "#444", background: "#fafafa" }}>
                <strong style={{ fontSize: "11px" }}>Instructions:</strong>
                {instructions.split("\n").filter(Boolean).map((line, i) => (
                  <p key={i} style={{ margin: "2px 0 2px 8px" }}>{line}</p>
                ))}
              </div>
            )}

            {/* Questions List (Text only) */}
            <div style={{ marginTop: "24px" }}>
              {questions.map((question, index) => (
                <div
                  key={question.id}
                  style={{
                    pageBreakInside: "avoid",
                    marginBottom: "16px",
                  }}
                >
                  <div style={{ display: "flex", gap: "8px", marginBottom: "6px" }}>
                    <span style={{ fontWeight: 800, fontSize: "13px", minWidth: "28px", color: "#000" }}>
                      Q{index + 1}.
                    </span>
                    <span style={{ fontSize: "13px", color: "#000", lineHeight: 1.5 }}>
                      {question.text || "(No question text)"}
                    </span>
                  </div>
                  
                  <div style={{ marginLeft: "36px", display: "flex", flexDirection: "column", gap: "4px" }}>
                    {question.options.map((option, optIdx) => (
                      <div key={optIdx} style={{ fontSize: "12px", color: "#333" }}>
                        <strong>{OPTION_LABELS[optIdx]}.</strong> {option || `Option ${OPTION_LABELS[optIdx]}`}
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            
            <div style={{ marginTop: "30px", textAlign: "center", fontSize: "11px", color: "#555", fontStyle: "italic" }}>
              Please mark your answers on the attached OMR sheet.
            </div>
          </div>

          {/* FINAL PAGE: OMR SHEET */}
          {omrImageUrl && (
            <div className="omr-sheet-page">
              {/* Using standard img tag. Next.js Image component doesn't handle blob URLs gracefully for print */}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img 
                alt="OMR Answer Sheet" 
                className="omr-sheet-image" 
                src={omrImageUrl} 
              />
            </div>
          )}
        </div>
      )}
    </>
  );
}
