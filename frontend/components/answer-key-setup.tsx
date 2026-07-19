"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useDropzone, type FileRejection } from "react-dropzone";
import { CheckIcon, FileIcon, KeyIcon, ScanIcon, UploadIcon } from "@/components/icons";
import { Alert, Spinner } from "@/components/ui";
import { api, getApiError } from "@/lib/api";
import type { AnswerMap, Exam } from "@/lib/types";
import { uploadPolicy, validateUploadFile } from "@/lib/upload-policy";
import { cn, fileSize, normalizeAnswerMap } from "@/lib/utils";

type AnswerKeyMethod = "manual" | "scan" | "csv";

interface CsvRow {
  question: number;
  answer: string;
}

const methods: Array<{ id: AnswerKeyMethod; label: string; description: string; icon: typeof KeyIcon }> = [
  { id: "manual", label: "Manual entry", description: "Choose each correct answer", icon: KeyIcon },
  { id: "scan", label: "Scan master", description: "Upload a filled master sheet", icon: ScanIcon },
  { id: "csv", label: "Import CSV", description: "Upload question and answer rows", icon: FileIcon },
];

function rejectionMessage(rejections: FileRejection[]) {
  const code = rejections[0]?.errors[0]?.code;
  if (code === "file-too-large") return `The selected file is larger than ${uploadPolicy.maxFileSizeMb} MB.`;
  if (code === "file-invalid-type") return "Choose a supported image, PDF, or CSV file.";
  return rejections[0]?.errors[0]?.message || "That file could not be selected.";
}

export function AnswerKeySetup({ exam, initialAnswers = {}, onSaved }: { exam: Exam; initialAnswers?: AnswerMap; onSaved?: (answers: AnswerMap) => void }) {
  const [method, setMethod] = useState<AnswerKeyMethod>("manual");
  const [answers, setAnswers] = useState<AnswerMap>(initialAnswers);
  const [masterFile, setMasterFile] = useState<File | null>(null);
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [csvRows, setCsvRows] = useState<CsvRow[]>([]);
  const [saving, setSaving] = useState(false);
  const [validatingMaster, setValidatingMaster] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    setAnswers(initialAnswers);
  }, [initialAnswers]);

  const options = useMemo(
    () => Array.from({ length: exam.options_per_question }, (_, index) => String.fromCharCode(65 + index)),
    [exam.options_per_question],
  );
  const answeredCount = Object.values(answers).filter(Boolean).length;
  const complete = answeredCount === exam.total_questions;

  const masterDropzone = useDropzone({
    accept: { "image/jpeg": [".jpg", ".jpeg"], "image/png": [".png"], "application/pdf": [".pdf"] },
    maxFiles: 1,
    maxSize: uploadPolicy.maxFileSizeMb * 1024 * 1024,
    multiple: false,
    disabled: saving || validatingMaster,
    onDropAccepted: (files) => void selectMaster(files[0]),
    onDropRejected: (rejections) => setError(rejectionMessage(rejections)),
  });

  async function selectMaster(file?: File) {
    if (!file) return;
    setValidatingMaster(true);
    setError("");
    setSuccess("");
    try {
      const issue = await validateUploadFile(file);
      if (issue) throw new Error(issue);
      setMasterFile(file);
    } catch (caught) {
      setMasterFile(null);
      setError(caught instanceof Error ? caught.message : "The master sheet could not be read.");
    } finally {
      setValidatingMaster(false);
    }
  }

  const csvDropzone = useDropzone({
    accept: { "text/csv": [".csv"], "application/vnd.ms-excel": [".csv"] },
    maxFiles: 1,
    maxSize: 2 * 1024 * 1024,
    multiple: false,
    onDropAccepted: (files) => void selectCsv(files[0]),
    onDropRejected: (rejections) => setError(rejectionMessage(rejections)),
  });

  async function selectCsv(file?: File) {
    if (!file) return;
    setError("");
    setSuccess("");
    try {
      const text = await file.text();
      const lines = text.replace(/^\uFEFF/, "").split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
      if (lines.length < 2) throw new Error("The CSV must include a header and at least one answer row.");
      const headers = lines[0].split(",").map((cell) => cell.trim().toLowerCase());
      const questionIndex = headers.indexOf("question");
      const answerIndex = headers.indexOf("answer");
      if (questionIndex < 0 || answerIndex < 0) throw new Error("Use the CSV columns “question” and “answer”.");
      const seen = new Set<number>();
      const rows = lines.slice(1).map((line, index) => {
        const cells = line.split(",").map((cell) => cell.trim().replace(/^"|"$/g, ""));
        const question = Number(cells[questionIndex]);
        const answer = (cells[answerIndex] || "").toUpperCase();
        if (!Number.isInteger(question) || question < 1 || question > exam.total_questions) throw new Error(`Row ${index + 2} has an invalid question number.`);
        if (!options.includes(answer)) throw new Error(`Row ${index + 2} must use one of: ${options.join(", ")}.`);
        if (seen.has(question)) throw new Error(`Question ${question} appears more than once.`);
        seen.add(question);
        return { question, answer };
      });
      if (rows.length !== exam.total_questions) throw new Error(`The file has ${rows.length} answers; this exam requires ${exam.total_questions}.`);
      setCsvRows(rows.sort((a, b) => a.question - b.question));
      setCsvFile(file);
    } catch (caught) {
      setCsvRows([]);
      setCsvFile(null);
      setError(caught instanceof Error ? caught.message : "The CSV could not be read.");
    }
  }

  function chooseMethod(next: AnswerKeyMethod) {
    setMethod(next);
    setError("");
    setSuccess("");
  }

  async function saveManual() {
    if (!complete) {
      setError(`Choose an answer for all ${exam.total_questions} questions before saving.`);
      return;
    }
    await save(async () => api.saveManualAnswerKey(exam.id, answers), "Manual answer key saved.");
  }

  async function saveScan() {
    if (!masterFile) { setError("Choose a completed master sheet first."); return; }
    await save(async () => api.scanAnswerKey(exam.id, masterFile), "Master sheet scanned and saved.");
  }

  async function saveCsv() {
    if (!csvFile || csvRows.length !== exam.total_questions) { setError("Choose a valid CSV with one row per question."); return; }
    await save(async () => api.uploadAnswerKeyCsv(exam.id, csvFile), "CSV answer key imported.");
  }

  async function save(request: () => Promise<unknown>, message: string) {
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const response = await request();
      const saved = normalizeAnswerMap(response);
      if (Object.keys(saved).length) setAnswers(saved);
      setSuccess(message);
      onSaved?.(Object.keys(saved).length ? saved : answers);
    } catch (caught) {
      setError(getApiError(caught, "The answer key could not be saved."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="surface-card overflow-hidden">
      <div className="border-b border-slate-200 px-5 py-5 sm:px-7">
        <div className="flex items-start gap-3">
          <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-brand-50 text-brand-600"><KeyIcon /></span>
          <div><h2 className="text-lg font-black text-slate-950">Add the answer key</h2><p className="mt-1 text-sm leading-6 text-slate-500">Choose the method that fits your workflow. Saving again replaces the current key.</p></div>
        </div>
      </div>

      <div className="border-b border-slate-200 bg-slate-50/70 p-2 sm:p-3" role="tablist" aria-label="Answer key methods">
        <div className="grid gap-2 sm:grid-cols-3">
          {methods.map((item) => {
            const Icon = item.icon;
            const active = method === item.id;
            return (
              <button aria-controls={`panel-${item.id}`} aria-selected={active} className={cn("flex items-center gap-3 rounded-xl border px-3 py-3 text-left transition", active ? "border-brand-200 bg-white text-brand-700 shadow-sm" : "border-transparent text-slate-600 hover:bg-white/80")} id={`tab-${item.id}`} key={item.id} onClick={() => chooseMethod(item.id)} role="tab" type="button">
                <span className={cn("grid h-9 w-9 shrink-0 place-items-center rounded-lg", active ? "bg-brand-50" : "bg-slate-200/70")}><Icon size={18} /></span>
                <span><span className="block text-sm font-extrabold">{item.label}</span><span className="hidden text-xs text-slate-400 lg:block">{item.description}</span></span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="p-5 sm:p-7">
        {error && <div className="mb-5"><Alert>{error}</Alert></div>}
        {success && <div className="mb-5"><Alert tone="success" title="Answer key ready">{success}</Alert></div>}

        {method === "manual" && (
          <div aria-labelledby="tab-manual" id="panel-manual" role="tabpanel">
            <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div><h3 className="font-extrabold text-slate-900">Select the correct option</h3><p className="mt-1 text-sm text-slate-500">Every question needs exactly one answer.</p></div>
              <span className={cn("w-fit rounded-full px-3 py-1.5 text-xs font-bold", complete ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600")}>{answeredCount} of {exam.total_questions} complete</span>
            </div>
            <div className="max-h-[560px] space-y-2 overflow-y-auto rounded-xl border border-slate-200 bg-slate-50/60 p-2 sm:p-3">
              {Array.from({ length: exam.total_questions }, (_, index) => {
                const question = String(index + 1);
                return (
                  <fieldset className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-3 sm:flex-row sm:items-center sm:justify-between" key={question}>
                    <legend className="sr-only">Correct answer for question {question}</legend>
                    <span className="text-sm font-extrabold text-slate-700">Question {question}</span>
                    <div className="flex gap-2">
                      {options.map((option) => {
                        const selected = answers[question] === option;
                        return (
                          <label className={cn("grid h-9 w-9 cursor-pointer place-items-center rounded-lg border text-sm font-black transition", selected ? "border-brand-600 bg-brand-600 text-white" : "border-slate-300 bg-white text-slate-600 hover:border-brand-300 hover:bg-brand-50")} key={option}>
                            <input checked={selected} className="sr-only" name={`question-${question}`} onChange={() => { setAnswers((current) => ({ ...current, [question]: option })); setError(""); setSuccess(""); }} type="radio" value={option} />
                            {option}
                          </label>
                        );
                      })}
                    </div>
                  </fieldset>
                );
              })}
            </div>
            <div className="mt-5 flex justify-end"><button className="button-primary min-w-40" disabled={saving || !complete} onClick={() => void saveManual()} type="button">{saving ? <><Spinner /> Saving…</> : <><CheckIcon size={17} /> Save answer key</>}</button></div>
          </div>
        )}

        {method === "scan" && (
          <div aria-labelledby="tab-scan" id="panel-scan" role="tabpanel">
            <div {...masterDropzone.getRootProps({ className: cn("flex min-h-64 cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-10 text-center transition", masterDropzone.isDragActive ? "border-brand-500 bg-brand-50" : "border-slate-300 bg-slate-50 hover:border-brand-400 hover:bg-brand-50/40") })}>
              <input {...masterDropzone.getInputProps()} />
              <span className="grid h-14 w-14 place-items-center rounded-2xl bg-white text-brand-600 shadow-sm">{validatingMaster ? <Spinner /> : <UploadIcon size={25} />}</span>
              {masterFile ? <><p className="mt-5 font-extrabold text-slate-900">{masterFile.name}</p><p className="mt-1 text-sm text-slate-500">{fileSize(masterFile.size)} · Content verified and ready to scan</p></> : <><p className="mt-5 font-extrabold text-slate-900">{validatingMaster ? "Checking file contents…" : "Drop your filled master sheet here"}</p><p className="mt-2 text-sm leading-6 text-slate-500">or click to choose a JPG, PNG, or single-page PDF up to {uploadPolicy.maxFileSizeMb} MB</p></>}
            </div>
            <div className="mt-5 flex justify-end"><button className="button-primary min-w-44" disabled={saving || validatingMaster || !masterFile} onClick={() => void saveScan()} type="button">{saving ? <><Spinner /> Detecting answers…</> : <><ScanIcon size={18} /> Scan and save key</>}</button></div>
          </div>
        )}

        {method === "csv" && (
          <div aria-labelledby="tab-csv" id="panel-csv" role="tabpanel">
            <div {...csvDropzone.getRootProps({ className: cn("flex min-h-52 cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-9 text-center transition", csvDropzone.isDragActive ? "border-brand-500 bg-brand-50" : "border-slate-300 bg-slate-50 hover:border-brand-400 hover:bg-brand-50/40") })}>
              <input {...csvDropzone.getInputProps()} />
              <span className="grid h-14 w-14 place-items-center rounded-2xl bg-white text-brand-600 shadow-sm"><FileIcon size={25} /></span>
              {csvFile ? <><p className="mt-5 font-extrabold text-slate-900">{csvFile.name}</p><p className="mt-1 text-sm text-slate-500">{csvRows.length} valid answer rows</p></> : <><p className="mt-5 font-extrabold text-slate-900">Drop a CSV answer key here</p><p className="mt-2 text-sm text-slate-500">Required headers: <span className="font-mono font-semibold text-slate-700">question,answer</span></p></>}
            </div>
            {csvRows.length > 0 && <div className="mt-4 overflow-hidden rounded-xl border border-slate-200"><div className="grid grid-cols-2 bg-slate-50 px-4 py-2 text-xs font-extrabold uppercase tracking-wider text-slate-500"><span>Question</span><span>Answer</span></div>{csvRows.slice(0, 6).map((row) => <div className="grid grid-cols-2 border-t border-slate-100 px-4 py-2 text-sm" key={row.question}><span>{row.question}</span><span className="font-bold text-brand-700">{row.answer}</span></div>)}{csvRows.length > 6 && <p className="border-t border-slate-100 px-4 py-2 text-xs text-slate-400">and {csvRows.length - 6} more rows</p>}</div>}
            <div className="mt-5 flex justify-end"><button className="button-primary min-w-40" disabled={saving || !csvFile} onClick={() => void saveCsv()} type="button">{saving ? <><Spinner /> Importing…</> : <><CheckIcon size={17} /> Import answer key</>}</button></div>
          </div>
        )}

        {success && <div className="mt-6 border-t border-slate-200 pt-6 text-right"><Link className="button-secondary" href={`/exams/${exam.id}`}>Continue to scan workspace</Link></div>}
      </div>
    </section>
  );
}
