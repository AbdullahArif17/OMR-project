"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { ArrowLeftIcon, CheckIcon, DownloadIcon, FileIcon } from "@/components/icons";
import { Alert, PageTitle, Spinner } from "@/components/ui";
import { api, getApiError } from "@/lib/api";
import { cn, safeFileName } from "@/lib/utils";

export default function GenerateSheetPage() {
  const [title, setTitle] = useState("OMR EXAMINATION SHEET");
  const [totalQuestions, setTotalQuestions] = useState(20);
  const [optionsPerQuestion, setOptionsPerQuestion] = useState<4 | 5>(4);
  const [includeName, setIncludeName] = useState(true);
  const [includeRoll, setIncludeRoll] = useState(true);
  
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");

  async function handleGenerate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setGenerating(true);
    
    try {
      const blob = await api.previewSheet({
        title: title.trim(),
        totalQuestions,
        optionsPerQuestion,
        includeName,
        includeRoll,
      });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${safeFileName(title) || "custom"}-omr-sheet.png`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (caught) {
      setError(getApiError(caught, "The sheet could not be generated."));
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div className="animate-fade-in space-y-7 max-w-4xl mx-auto">
      <div>
        <Link className="button-ghost -ml-3 mb-3" href="/dashboard"><ArrowLeftIcon size={17} /> Back to dashboard</Link>
        <PageTitle 
          eyebrow="Printable Templates" 
          title="Generate Custom OMR Sheet" 
          description="Create a blank OMR sheet to print for tests that don't need a saved exam workspace yet." 
        />
      </div>

      {error && <Alert>{error}</Alert>}

      <form className="surface-card overflow-hidden" onSubmit={handleGenerate}>
        <div className="border-b border-slate-200 px-5 py-5 sm:px-7">
          <div className="flex items-start gap-3">
            <span className="grid h-11 w-11 place-items-center rounded-xl bg-brand-50 text-brand-600"><FileIcon /></span>
            <div>
              <h2 className="text-lg font-black text-slate-950">Sheet settings</h2>
              <p className="mt-1 text-sm leading-6 text-slate-500">Configure the layout of your printable sheet.</p>
            </div>
          </div>
        </div>
        
        <div className="grid gap-6 p-5 sm:p-7 lg:grid-cols-2">
          <div className="lg:col-span-2">
            <label className="field-label" htmlFor="sheet-title">Sheet title</label>
            <input className="text-field" id="sheet-title" maxLength={60} onChange={(event) => setTitle(event.target.value)} placeholder="e.g. OMR EXAMINATION SHEET" required value={title} />
            <p className="mt-2 text-xs text-slate-400">Printed at the top of the sheet.</p>
          </div>
          
          <div>
            <label className="field-label" htmlFor="question-count">Total questions <span className="text-rose-500">*</span></label>
            <input className="text-field" id="question-count" max={40} min={10} onChange={(event) => setTotalQuestions(parseInt(event.target.value, 10) || 0)} required type="number" value={totalQuestions.toString()} />
            <p className="mt-2 text-xs text-slate-400">Between 10 and 40 questions.</p>
          </div>
          
          <fieldset>
            <legend className="field-label">Options per question</legend>
            <div className="grid gap-3 sm:grid-cols-2">
              {([4, 5] as const).map((count) => {
                const selected = optionsPerQuestion === count;
                return (
                  <label className={cn("flex cursor-pointer items-center justify-between rounded-xl border p-3 transition", selected ? "border-brand-500 bg-brand-50 ring-2 ring-brand-100" : "border-slate-300 bg-white hover:border-slate-400")} key={count}>
                    <span className="text-sm font-extrabold text-slate-900">{count} options</span>
                    <span className={cn("grid h-5 w-5 place-items-center rounded-full border", selected ? "border-brand-600 bg-brand-600 text-white" : "border-slate-300")}>{selected && <CheckIcon size={13} />}</span>
                    <input checked={selected} className="sr-only" name="options" onChange={() => setOptionsPerQuestion(count)} type="radio" value={count} />
                  </label>
                );
              })}
            </div>
          </fieldset>

          <fieldset className="lg:col-span-2 mt-2">
            <legend className="field-label mb-3">Student Information Fields</legend>
            <div className="flex flex-col sm:flex-row gap-5">
              <label className="flex items-center gap-3 cursor-pointer">
                <input 
                  checked={includeName} 
                  className="h-5 w-5 rounded border-slate-300 text-brand-600 focus:ring-brand-600" 
                  onChange={(e) => setIncludeName(e.target.checked)} 
                  type="checkbox" 
                />
                <span className="text-sm font-bold text-slate-700">Include Name Grid (A-Z)</span>
              </label>
              
              <label className="flex items-center gap-3 cursor-pointer">
                <input 
                  checked={includeRoll} 
                  className="h-5 w-5 rounded border-slate-300 text-brand-600 focus:ring-brand-600" 
                  onChange={(e) => setIncludeRoll(e.target.checked)} 
                  type="checkbox" 
                />
                <span className="text-sm font-bold text-slate-700">Include Roll Number Grid (0-9)</span>
              </label>
            </div>
            <p className="mt-3 text-xs text-slate-500">Note: Without student fields, the scanner will not automatically assign results to students.</p>
          </fieldset>
        </div>
        
        <div className="flex gap-3 border-t border-slate-200 bg-slate-50/60 px-5 py-4 sm:items-center sm:justify-end sm:px-7">
          <button className="button-primary min-w-44" disabled={generating} type="submit">{generating ? <><Spinner /> Generating…</> : <><DownloadIcon size={17} /> Download PNG Sheet</>}</button>
        </div>
      </form>
    </div>
  );
}
