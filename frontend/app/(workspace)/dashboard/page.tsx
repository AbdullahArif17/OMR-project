"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/components/auth-provider";
import { ExamCard } from "@/components/exam-card";
import { CalendarIcon, ExamIcon, PlusIcon, SearchIcon, SparkleIcon } from "@/components/icons";
import { Alert, EmptyState, PageTitle, RetryButton, Skeleton, StatCard } from "@/components/ui";
import { api, getApiError } from "@/lib/api";
import type { Exam } from "@/lib/types";

export default function DashboardPage() {
  const { user } = useAuth();
  const [exams, setExams] = useState<Exam[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [deletingId, setDeletingId] = useState("");

  const loadExams = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setExams(await api.listExams());
    } catch (caught) {
      setError(getApiError(caught, "We could not load your exams."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadExams();
  }, [loadExams]);

  const filtered = useMemo(() => {
    const search = query.trim().toLowerCase();
    if (!search) return exams;
    return exams.filter((exam) => `${exam.name} ${exam.subject || ""}`.toLowerCase().includes(search));
  }, [exams, query]);

  const createdThisMonth = useMemo(() => {
    const now = new Date();
    return exams.filter((exam) => {
      const date = new Date(exam.created_at);
      return date.getMonth() === now.getMonth() && date.getFullYear() === now.getFullYear();
    }).length;
  }, [exams]);

  async function deleteExam(exam: Exam) {
    if (!window.confirm(`Delete “${exam.name}”? Its answer key and saved results will also be removed.`)) return;
    setDeletingId(exam.id);
    setError("");
    try {
      await api.deleteExam(exam.id);
      setExams((current) => current.filter((item) => item.id !== exam.id));
    } catch (caught) {
      setError(getApiError(caught, "The exam could not be deleted."));
    } finally {
      setDeletingId("");
    }
  }

  const firstName = user?.name.split(/\s+/)[0] || "Teacher";
  const isAdmin = user?.role === "admin";

  return (
    <div className="animate-fade-in space-y-8">
      <PageTitle
        eyebrow={isAdmin ? "Admin dashboard" : "Teacher dashboard"}
        title={`Good to see you, ${firstName}`}
        description={
          isAdmin
            ? "Oversee every assessment, scan answer sheets, and review results across all teachers."
            : "Create assessments, scan answer sheets, and keep every result organized."
        }
        actions={<Link className="button-primary" href="/exams/create"><PlusIcon size={18} /> Create new exam</Link>}
      />

      {error && <Alert>{error}</Alert>}

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="Exam summary">
        {loading ? Array.from({ length: 4 }, (_, index) => <Skeleton className="h-32" key={index} />) : (
          <>
            <StatCard accent="brand" icon={<ExamIcon />} label="Total exams" note="All assessments" value={exams.length} />
            <StatCard accent="emerald" icon={<CalendarIcon />} label="Created this month" note="Current month" value={createdThisMonth} />
            <StatCard accent="amber" icon={<SparkleIcon />} label="Questions prepared" note="Across all exams" value={exams.reduce((sum, exam) => sum + exam.total_questions, 0)} />
            <StatCard accent="rose" icon={<span className="text-lg font-black">A–E</span>} label="Answer formats" note="Four or five options" value={new Set(exams.map((exam) => exam.options_per_question)).size || 0} />
          </>
        )}
      </section>

      <section>
        <div className="mb-5 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div><h2 className="text-xl font-black tracking-tight text-slate-950">{isAdmin ? "All exams" : "Your exams"}</h2><p className="mt-1 text-sm text-slate-500">Choose an exam to scan sheets or view results.</p></div>
          {!loading && exams.length > 0 && (
            <label className="relative block sm:w-72">
              <span className="sr-only">Search exams</span>
              <SearchIcon className="pointer-events-none absolute left-3.5 top-3 text-slate-400" size={18} />
              <input className="text-field py-2.5 pl-10" onChange={(event) => setQuery(event.target.value)} placeholder="Search exams…" type="search" value={query} />
            </label>
          )}
        </div>

        {loading ? (
          <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">{Array.from({ length: 6 }, (_, index) => <Skeleton className="h-72" key={index} />)}</div>
        ) : error && exams.length === 0 ? (
          <div className="surface-card flex min-h-72 flex-col items-center justify-center p-8 text-center"><span className="grid h-14 w-14 place-items-center rounded-2xl bg-rose-50 text-rose-600"><ExamIcon /></span><h2 className="mt-5 text-lg font-black">Exams are unavailable</h2><p className="mt-2 max-w-md text-sm leading-6 text-slate-500">Once the API is reachable, your assessments will appear here.</p><RetryButton onClick={() => void loadExams()} /></div>
        ) : exams.length === 0 ? (
          <EmptyState action={<Link className="button-primary" href="/exams/create"><PlusIcon size={18} /> Create your first exam</Link>} description="Set up the assessment details and add an answer key. You’ll be ready to scan in a few minutes." icon={<ExamIcon size={26} />} title="Your first exam starts here" />
        ) : filtered.length === 0 ? (
          <EmptyState action={<button className="button-secondary" onClick={() => setQuery("")} type="button">Clear search</button>} description={`No exam matches “${query}”. Try a name or subject.`} icon={<SearchIcon size={25} />} title="No matching exams" />
        ) : (
          <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
            {filtered.map((exam) => <ExamCard deleting={deletingId === exam.id} exam={exam} key={exam.id} onDelete={deleteExam} />)}
          </div>
        )}
      </section>
    </div>
  );
}
