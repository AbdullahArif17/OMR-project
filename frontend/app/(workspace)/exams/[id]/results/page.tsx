"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeftIcon, ChartIcon, DownloadIcon, FilterIcon, SearchIcon, UsersIcon } from "@/components/icons";
import { ResultsTable } from "@/components/results-table";
import { Alert, EmptyState, PageTitle, RetryButton, Skeleton, Spinner, StatCard } from "@/components/ui";
import { api, getApiError } from "@/lib/api";
import type { Exam, Result, ResultsSummary } from "@/lib/types";
import { calculateSummary, cn, safeFileName, studentClass, studentName, studentRoll } from "@/lib/utils";

type SortOption = "recent" | "score-desc" | "score-asc" | "name";
type StatusFilter = "all" | "pass" | "review";

export default function ResultsPage() {
  const params = useParams<{ id: string }>();
  const examId = params.id;
  const [exam, setExam] = useState<Exam | null>(null);
  const [results, setResults] = useState<Result[]>([]);
  const [serverSummary, setServerSummary] = useState<ResultsSummary | undefined>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [sort, setSort] = useState<SortOption>("recent");
  const [exporting, setExporting] = useState(false);

  const loadResults = useCallback(async () => {
    setLoading(true);
    setError("");
    const [examResponse, resultsResponse] = await Promise.allSettled([api.getExam(examId), api.getResults(examId)]);
    if (examResponse.status === "fulfilled") setExam(examResponse.value);
    if (resultsResponse.status === "fulfilled") {
      setResults(resultsResponse.value.results || []);
      setServerSummary(resultsResponse.value.summary);
    }
    if (examResponse.status === "rejected") setError(getApiError(examResponse.reason, "The exam could not be loaded."));
    else if (resultsResponse.status === "rejected") setError(getApiError(resultsResponse.reason, "Results could not be loaded."));
    setLoading(false);
  }, [examId]);

  useEffect(() => {
    void loadResults();
  }, [loadResults]);

  const summary = useMemo(() => ({ ...calculateSummary(results), ...(serverSummary || {}) }), [results, serverSummary]);

  const filtered = useMemo(() => {
    const search = query.trim().toLowerCase();
    const matching = results.filter((result) => {
      const textMatch = !search || `${studentName(result)} ${studentRoll(result)} ${studentClass(result)}`.toLowerCase().includes(search);
      const statusMatch = status === "all" || (status === "pass" ? result.percentage >= 60 : result.percentage < 60);
      return textMatch && statusMatch;
    });
    return [...matching].sort((a, b) => {
      if (sort === "score-desc") return b.percentage - a.percentage;
      if (sort === "score-asc") return a.percentage - b.percentage;
      if (sort === "name") return studentName(a).localeCompare(studentName(b));
      return new Date(b.scanned_at).getTime() - new Date(a.scanned_at).getTime();
    });
  }, [query, results, sort, status]);

  const distribution = useMemo(() => [
    { label: "90–100%", count: results.filter((result) => result.percentage >= 90).length, color: "bg-emerald-500" },
    { label: "80–89%", count: results.filter((result) => result.percentage >= 80 && result.percentage < 90).length, color: "bg-teal-500" },
    { label: "60–79%", count: results.filter((result) => result.percentage >= 60 && result.percentage < 80).length, color: "bg-brand-500" },
    { label: "40–59%", count: results.filter((result) => result.percentage >= 40 && result.percentage < 60).length, color: "bg-amber-500" },
    { label: "Below 40%", count: results.filter((result) => result.percentage < 40).length, color: "bg-rose-500" },
  ], [results]);

  async function exportCsv() {
    if (!exam) return;
    setExporting(true);
    setError("");
    try {
      const blob = await api.exportResults(exam.id);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${safeFileName(exam.name) || "exam"}-results.csv`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (caught) {
      setError(getApiError(caught, "The results export could not be prepared."));
    } finally {
      setExporting(false);
    }
  }

  if (loading) {
    return <div className="space-y-6"><Skeleton className="h-28" /><div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{Array.from({ length: 4 }, (_, index) => <Skeleton className="h-32" key={index} />)}</div><Skeleton className="h-72" /><Skeleton className="h-96" /></div>;
  }

  if (!exam) {
    return <div className="surface-card flex min-h-[420px] flex-col items-center justify-center p-8 text-center"><span className="grid h-14 w-14 place-items-center rounded-2xl bg-rose-50 text-rose-600"><ChartIcon /></span><h1 className="mt-5 text-xl font-black">Results unavailable</h1><p className="mt-2 max-w-md text-sm leading-6 text-slate-500">{error || "This exam may no longer exist."}</p><RetryButton onClick={() => void loadResults()} /><Link className="button-ghost mt-2" href="/dashboard">Return to dashboard</Link></div>;
  }

  return (
    <div className="animate-fade-in space-y-7">
      <div><Link className="button-ghost -ml-3 mb-3" href={`/exams/${exam.id}`}><ArrowLeftIcon size={17} /> Back to scan workspace</Link><PageTitle eyebrow={exam.subject || "Exam analytics"} title={`${exam.name} results`} description="Review class performance, find individual students, and export the complete grading record." actions={<button className="button-primary" disabled={exporting || results.length === 0} onClick={() => void exportCsv()} type="button">{exporting ? <><Spinner /> Preparing…</> : <><DownloadIcon size={18} /> Export CSV</>}</button>} /></div>
      {error && <Alert>{error}</Alert>}

      {results.length === 0 ? (
        <EmptyState action={<Link className="button-primary" href={`/exams/${exam.id}`}><ArrowLeftIcon size={17} /> Scan student sheets</Link>} description="Processed sheets will appear here with scores, grades, and question-level details." icon={<ChartIcon size={26} />} title="No results yet" />
      ) : (
        <>
          <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="Results summary">
            <StatCard accent="brand" icon={<UsersIcon />} label="Total scans" note="Saved student results" value={summary.total_scans ?? summary.total_students ?? results.length} />
            <StatCard accent="emerald" icon={<ChartIcon />} label="Average score" note={`${Number(summary.average_percentage || 0).toFixed(1)}% class average`} value={`${Number(summary.average_score).toFixed(1)}/${exam.total_questions}`} />
            <StatCard accent="amber" icon={<span className="text-base font-black">↑↓</span>} label="Score range" note="Lowest to highest" value={`${Number(summary.lowest_score).toFixed(0)}–${Number(summary.highest_score).toFixed(0)}`} />
            <StatCard accent="rose" icon={<span className="text-base font-black">%</span>} label="Pass rate" note="60% or above" value={`${Number(summary.pass_rate).toFixed(1)}%`} />
          </section>

          <section className="surface-card p-5 sm:p-6" aria-labelledby="distribution-heading">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between"><div><h2 className="text-lg font-black text-slate-950" id="distribution-heading">Score distribution</h2><p className="mt-1 text-sm text-slate-500">See how the class is spread across performance bands.</p></div><p className="text-xs font-semibold text-slate-400">{results.length} graded sheet{results.length === 1 ? "" : "s"}</p></div>
            <div className="mt-6 grid gap-4 sm:grid-cols-5">
              {distribution.map((band) => {
                const percent = results.length ? (band.count / results.length) * 100 : 0;
                return <div key={band.label}><div className="flex items-center justify-between text-xs"><span className="font-bold text-slate-600">{band.label}</span><span className="font-black text-slate-900">{band.count}</span></div><div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100"><div className={cn("h-full rounded-full transition-all duration-500", band.color)} style={{ width: `${percent}%` }} /></div><p className="mt-1.5 text-[11px] text-slate-400">{percent.toFixed(0)}% of class</p></div>;
              })}
            </div>
          </section>

          <section>
            <div className="mb-4 flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
              <div><h2 className="text-xl font-black tracking-tight text-slate-950">Student results</h2><p className="mt-1 text-sm text-slate-500">{filtered.length} of {results.length} results shown</p></div>
              <div className="grid gap-3 sm:grid-cols-3 xl:w-[720px]">
                <label className="relative sm:col-span-1"><span className="sr-only">Search students</span><SearchIcon className="pointer-events-none absolute left-3.5 top-3 text-slate-400" size={18} /><input className="text-field py-2.5 pl-10" onChange={(event) => setQuery(event.target.value)} placeholder="Search student…" type="search" value={query} /></label>
                <label className="relative"><span className="sr-only">Filter by status</span><FilterIcon className="pointer-events-none absolute left-3.5 top-3 text-slate-400" size={17} /><select className="text-field appearance-none py-2.5 pl-10" onChange={(event) => setStatus(event.target.value as StatusFilter)} value={status}><option value="all">All statuses</option><option value="pass">Passed</option><option value="review">Needs review</option></select></label>
                <label><span className="sr-only">Sort results</span><select className="text-field appearance-none py-2.5" onChange={(event) => setSort(event.target.value as SortOption)} value={sort}><option value="recent">Newest first</option><option value="score-desc">Highest score</option><option value="score-asc">Lowest score</option><option value="name">Student name</option></select></label>
              </div>
            </div>
            {filtered.length > 0 ? <ResultsTable results={filtered} /> : <EmptyState action={<button className="button-secondary" onClick={() => { setQuery(""); setStatus("all"); }} type="button">Clear filters</button>} description="Try a different student, roll number, class, or status." icon={<SearchIcon size={25} />} title="No matching results" />}
          </section>
        </>
      )}
    </div>
  );
}
