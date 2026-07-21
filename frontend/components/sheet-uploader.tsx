"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useDropzone, type FileRejection } from "react-dropzone";
import { AlertIcon, FileIcon, ScanIcon, TrashIcon, UploadIcon } from "@/components/icons";
import { Alert, Spinner } from "@/components/ui";
import { api, getApiError } from "@/lib/api";
import type { ScanBatchPayload, ScanFailure, ScanSheetInput } from "@/lib/types";
import {
  fileFingerprint,
  uploadPolicy,
  validateUploadFile,
} from "@/lib/upload-policy";
import { cn, fileSize, randomId } from "@/lib/utils";

interface QueuedSheet extends ScanSheetInput {
  queueId: string;
}

type ProcessingPhase = "idle" | "uploading" | "scanning";

function fileRejectionMessage(rejections: FileRejection[]) {
  const count = rejections.length;
  const first = rejections[0]?.errors[0];
  if (first?.code === "file-too-large") {
    return `${count === 1 ? "A file is" : `${count} files are`} larger than the ${uploadPolicy.maxFileSizeMb} MB limit.`;
  }
  if (first?.code === "too-many-files") {
    return `Choose no more than ${uploadPolicy.maxFiles} files in a batch.`;
  }
  return first?.message || "One or more files could not be added.";
}

function failureBelongsToFile(failure: ScanFailure, filename: string) {
  return (
    failure.filename === filename ||
    failure.filename.startsWith(`${filename}:`) ||
    failure.filename.startsWith(`${filename}#page-`)
  );
}

export function SheetUploader({
  examId,
  hasAnswerKey,
  onComplete,
}: {
  examId: string;
  hasAnswerKey: boolean;
  onComplete: (payload: ScanBatchPayload) => void;
}) {
  const [sheets, setSheets] = useState<QueuedSheet[]>([]);
  const [validating, setValidating] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [phase, setPhase] = useState<ProcessingPhase>("idle");
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const activeRequest = useRef<AbortController | null>(null);
  const submissionKey = useRef<string | null>(null);

  useEffect(() => () => activeRequest.current?.abort(), []);

  const queuedBytes = useMemo(
    () => sheets.reduce((total, sheet) => total + sheet.file.size, 0),
    [sheets],
  );

  async function addFiles(files: File[]) {
    submissionKey.current = null;
    setValidating(true);
    setError("");
    setNotice("");
    try {
      const validation = await Promise.all(
        files.map(async (file) => ({ file, issue: await validateUploadFile(file) })),
      );
      const issues = validation
        .map(({ issue }) => issue)
        .filter((issue): issue is string => Boolean(issue));
      const fingerprints = new Set(sheets.map((sheet) => fileFingerprint(sheet.file)));
      const accepted: QueuedSheet[] = [];
      let totalBytes = queuedBytes;
      let availableSlots = Math.max(0, uploadPolicy.maxFiles - sheets.length);

      for (const { file, issue } of validation) {
        if (issue) continue;
        const fingerprint = fileFingerprint(file);
        if (fingerprints.has(fingerprint)) {
          issues.push(`${file.name}: already in the queue`);
          continue;
        }
        if (availableSlots === 0) {
          issues.push(`The queue is limited to ${uploadPolicy.maxFiles} top-level files.`);
          break;
        }
        if (totalBytes + file.size > uploadPolicy.maxBatchSizeMb * 1024 * 1024) {
          issues.push(`The queued upload would exceed ${uploadPolicy.maxBatchSizeMb} MB in total.`);
          continue;
        }
        fingerprints.add(fingerprint);
        totalBytes += file.size;
        availableSlots -= 1;
        accepted.push({
          file,
          studentName: "",
          rollNumber: "",
          className: "",
          queueId: randomId(),
        });
      }

      if (accepted.length > 0) setSheets((current) => [...current, ...accepted]);
      setError([...new Set(issues)].join(" "));
    } finally {
      setValidating(false);
    }
  }

  const dropzone = useDropzone({
    accept: {
      "image/jpeg": [".jpg", ".jpeg"],
      "image/png": [".png"],
      "application/pdf": [".pdf"],
      "application/zip": [".zip"],
      "application/x-zip-compressed": [".zip"],
    },
    maxFiles: uploadPolicy.maxFiles,
    maxSize: uploadPolicy.maxFileSizeMb * 1024 * 1024,
    multiple: true,
    disabled:
      validating || processing || !hasAnswerKey || sheets.length >= uploadPolicy.maxFiles,
    onDropAccepted: (files) => void addFiles(files),
    onDropRejected: (rejections) => setError(fileRejectionMessage(rejections)),
  });

  const duplicateRolls = useMemo(() => {
    const counts = sheets.reduce<Record<string, number>>((all, sheet) => {
      const roll = sheet.rollNumber.trim().toLowerCase();
      if (roll) all[roll] = (all[roll] || 0) + 1;
      return all;
    }, {});
    return new Set(
      Object.entries(counts)
        .filter(([, count]) => count > 1)
        .map(([roll]) => roll),
    );
  }, [sheets]);

  function updateSheet(
    queueId: string,
    field: "studentName" | "rollNumber" | "className",
    value: string,
  ) {
    submissionKey.current = null;
    setSheets((current) =>
      current.map((sheet) => (sheet.queueId === queueId ? { ...sheet, [field]: value } : sheet)),
    );
    setError("");
  }

  function removeSheet(queueId: string) {
    submissionKey.current = null;
    setSheets((current) => current.filter((sheet) => sheet.queueId !== queueId));
    setNotice("");
  }

  function cancelProcessing() {
    activeRequest.current?.abort();
  }

  async function processSheets() {
    if (!hasAnswerKey) {
      setError("Add an answer key before scanning student sheets.");
      return;
    }
    if (sheets.length === 0) {
      setError("Add at least one student sheet to scan.");
      return;
    }
    if (duplicateRolls.size > 0) {
      setError("Roll numbers must be unique within this upload batch.");
      return;
    }

    const controller = new AbortController();
    const idempotencyKey = submissionKey.current ?? randomId();
    submissionKey.current = idempotencyKey;
    activeRequest.current = controller;
    setProcessing(true);
    setPhase("uploading");
    setProgress(1);
    setError("");
    setNotice("");
    try {
      const payload = await api.scanSheets(examId, sheets, {
        idempotencyKey,
        signal: controller.signal,
        onProgress: (value) => {
          setProgress(value);
          if (value >= 95) setPhase("scanning");
        },
      });
      setProgress(100);
      submissionKey.current = null;
      onComplete(payload);

      const failures = payload.errors || [];
      if (failures.length === 0) {
        setSheets([]);
        setNotice(`${payload.results.length} sheet${payload.results.length === 1 ? "" : "s"} graded and saved.`);
      } else {
        const failedInputs = sheets.filter((sheet) =>
          failures.some((failure) => failureBelongsToFile(failure, sheet.file.name)),
        );
        setSheets(failedInputs.length > 0 ? failedInputs : sheets);
        setNotice(
          `${payload.results.length} result${payload.results.length === 1 ? "" : "s"} saved. Files needing review remain queued.`,
        );
      }
    } catch (caught) {
      setError(getApiError(caught, "The sheets could not be processed."));
    } finally {
      activeRequest.current = null;
      setProcessing(false);
      setPhase("idle");
    }
  }

  return (
    <section className="surface-card overflow-hidden">
      <div className="border-b border-slate-200 p-5 sm:p-6">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-brand-50 text-brand-600">
              <ScanIcon />
            </span>
            <div>
              <h2 className="text-lg font-black text-slate-950">Scan student sheets</h2>
              <p className="mt-1 text-sm leading-6 text-slate-500">
                Add clear images, PDFs, or one ZIP archive. Every file is verified before upload.
              </p>
            </div>
          </div>
          {sheets.length > 0 && (
            <span className="hidden rounded-full bg-brand-50 px-3 py-1 text-xs font-extrabold text-brand-700 sm:block">
              {sheets.length} queued
            </span>
          )}
        </div>
      </div>

      <div className="p-5 sm:p-6">
        {!hasAnswerKey && (
          <div className="mb-5">
            <Alert title="Answer key required">
              Save an answer key first; grading cannot run without the correct answers.
            </Alert>
          </div>
        )}
        {error && <div className="mb-5"><Alert>{error}</Alert></div>}
        {notice && <div className="mb-5"><Alert tone="success">{notice}</Alert></div>}

        <div
          {...dropzone.getRootProps({
            className: cn(
              "flex min-h-52 flex-col items-center justify-center rounded-2xl border-2 border-dashed px-5 py-9 text-center transition",
              !hasAnswerKey
                ? "cursor-not-allowed border-slate-200 bg-slate-100/70 opacity-70"
                : dropzone.isDragActive
                  ? "cursor-copy border-brand-500 bg-brand-50"
                  : "cursor-pointer border-slate-300 bg-slate-50 hover:border-brand-400 hover:bg-brand-50/40",
            ),
          })}
        >
          <input {...dropzone.getInputProps()} />
          <span className="grid h-14 w-14 place-items-center rounded-2xl bg-white text-brand-600 shadow-sm">
            {validating ? <Spinner /> : <UploadIcon size={25} />}
          </span>
          <p className="mt-5 font-extrabold text-slate-900">
            {validating
              ? "Checking file contents…"
              : dropzone.isDragActive
                ? "Release to add these sheets"
                : "Drag and drop student sheets"}
          </p>
          <p className="mt-2 max-w-lg text-sm leading-6 text-slate-500">
            or click to browse · JPG, PNG, PDF, or ZIP · {uploadPolicy.maxFiles} files · {uploadPolicy.maxFileSizeMb} MB each · {uploadPolicy.maxBatchSizeMb} MB total
          </p>
        </div>

        <div className="mt-4 grid gap-2 rounded-xl border border-slate-200 bg-slate-50 p-4 text-xs leading-5 text-slate-600 sm:grid-cols-3">
          <p><strong className="text-slate-800">Frame:</strong> include the full bubble grid with no cropped rows.</p>
          <p><strong className="text-slate-800">Light:</strong> avoid glare, heavy shadows, blur, and very dark backgrounds.</p>
          <p><strong className="text-slate-800">Marks:</strong> fill one bubble per row cleanly; uncertain sheets are rejected for review.</p>
        </div>

        {sheets.length > 0 && (
          <div className="mt-6">
            <div className="mb-3 flex items-center justify-between gap-4">
              <div>
                <h3 className="text-sm font-extrabold text-slate-900">Student information</h3>
                <p className="mt-0.5 text-xs text-slate-400">{fileSize(queuedBytes)} queued in total</p>
              </div>
              <button
                className="text-xs font-bold text-slate-500 hover:text-rose-600"
                disabled={processing || validating}
                onClick={() => { submissionKey.current = null; setSheets([]); setNotice(""); }}
                type="button"
              >
                Clear all
              </button>
            </div>
            <div className="space-y-3">
              {sheets.map((sheet, index) => {
                const duplicate = duplicateRolls.has(sheet.rollNumber.trim().toLowerCase());
                return (
                  <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-3 sm:p-4" key={sheet.queueId}>
                    <div className="mb-3 flex items-center gap-3">
                      <span className="grid h-9 w-9 place-items-center rounded-lg bg-white text-brand-600 shadow-sm"><FileIcon size={18} /></span>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-extrabold text-slate-800">{sheet.file.name}</p>
                        <p className="text-xs text-slate-400">{fileSize(sheet.file.size)} · File {index + 1}</p>
                      </div>
                      <button
                        aria-label={`Remove ${sheet.file.name}`}
                        className="grid h-9 w-9 place-items-center rounded-lg text-slate-400 hover:bg-rose-50 hover:text-rose-600"
                        disabled={processing || validating}
                        onClick={() => removeSheet(sheet.queueId)}
                        type="button"
                      >
                        <TrashIcon size={17} />
                      </button>
                    </div>
                    <div className="grid gap-3 md:grid-cols-3">
                      <div>
                        <label className="sr-only" htmlFor={`name-${sheet.queueId}`}>Student name for {sheet.file.name}</label>
                        <input className="text-field py-2.5" disabled={processing} id={`name-${sheet.queueId}`} maxLength={255} onChange={(event) => updateSheet(sheet.queueId, "studentName", event.target.value)} placeholder="Student name" value={sheet.studentName} />
                      </div>
                      <div>
                        <label className="sr-only" htmlFor={`roll-${sheet.queueId}`}>Roll number for {sheet.file.name}</label>
                        <input aria-invalid={duplicate} className={cn("text-field py-2.5", duplicate && "border-rose-400 focus:border-rose-500 focus:ring-rose-100")} disabled={processing} id={`roll-${sheet.queueId}`} maxLength={50} onChange={(event) => updateSheet(sheet.queueId, "rollNumber", event.target.value)} placeholder="Roll number" value={sheet.rollNumber} />
                        {duplicate && <p className="mt-1 flex items-center gap-1 text-xs text-rose-600"><AlertIcon size={12} /> Duplicate roll number</p>}
                      </div>
                      <div>
                        <label className="sr-only" htmlFor={`class-${sheet.queueId}`}>Class for {sheet.file.name}</label>
                        <input className="text-field py-2.5" disabled={processing} id={`class-${sheet.queueId}`} maxLength={50} onChange={(event) => updateSheet(sheet.queueId, "className", event.target.value)} placeholder="Class / section" value={sheet.className} />
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {processing && (
          <div className="mt-6 rounded-xl border border-brand-100 bg-brand-50 p-4" role="status">
            <div className="flex items-center justify-between text-sm">
              <span className="inline-flex items-center gap-2 font-extrabold text-brand-800">
                <Spinner className="h-4 w-4" />
                {phase === "uploading" ? "Securely uploading sheets…" : "Detecting and grading bubbles…"}
              </span>
              <span className="font-black text-brand-700">{progress}%</span>
            </div>
            <div
              aria-label="Scan progress"
              aria-valuemax={100}
              aria-valuemin={0}
              aria-valuenow={progress}
              className="mt-3 h-2 overflow-hidden rounded-full bg-brand-100"
              role="progressbar"
            >
              <div className="h-full rounded-full bg-brand-600 transition-all duration-300" style={{ width: `${progress}%` }} />
            </div>
            <p className="mt-2 text-xs text-brand-700">
              {phase === "uploading"
                ? "Keep this page open while files are transferred."
                : "Upload complete. Each page is being validated before a result is saved."}
            </p>
          </div>
        )}

        <div className="mt-6 flex flex-col-reverse gap-3 border-t border-slate-200 pt-5 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs leading-5 text-slate-400">
            PDF pages and ZIP contents are expanded securely by the server and count toward the sheet limit.
          </p>
          <div className="flex shrink-0 gap-2">
            {processing && (
              <button className="button-secondary" onClick={cancelProcessing} type="button">
                Cancel
              </button>
            )}
            <button
              className="button-primary shrink-0 sm:min-w-44"
              disabled={processing || validating || sheets.length === 0 || !hasAnswerKey || duplicateRolls.size > 0}
              onClick={() => void processSheets()}
              type="button"
            >
              {processing ? <><Spinner /> Processing…</> : <><ScanIcon size={18} /> Process {sheets.length || ""} sheet{sheets.length === 1 ? "" : "s"}</>}
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
