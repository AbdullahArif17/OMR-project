"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/auth-provider";
import { ArrowRightIcon, CheckIcon, LockIcon, MailIcon, ScanIcon, ShieldIcon, SparkleIcon } from "@/components/icons";
import { Logo } from "@/components/logo";
import { Alert, Spinner } from "@/components/ui";

export default function LandingPage() {
  const router = useRouter();
  const { user, loading, allowDemo, signIn, continueInDemo } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await signIn(email.trim(), password);
      router.push("/dashboard");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Sign in failed. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  function handleDemo() {
    continueInDemo();
    router.push("/dashboard");
  }

  return (
    <main className="min-h-screen overflow-hidden bg-white">
      <div className="relative bg-[#101a33] text-white">
        <div className="absolute inset-0 overflow-hidden" aria-hidden="true">
          <div className="absolute -left-32 top-20 h-80 w-80 rounded-full bg-brand-600/25 blur-3xl" />
          <div className="absolute -right-24 -top-24 h-96 w-96 rounded-full bg-cyan-400/10 blur-3xl" />
          <div className="absolute inset-0 opacity-[0.06]" style={{ backgroundImage: "radial-gradient(#fff 1px, transparent 1px)", backgroundSize: "28px 28px" }} />
        </div>
        <nav className="relative mx-auto flex max-w-7xl items-center justify-between px-5 py-5 sm:px-8 lg:px-10" aria-label="Main navigation">
          <Logo light />
          <div className="flex items-center gap-3">
            <a className="hidden rounded-lg px-3 py-2 text-sm font-semibold text-slate-300 transition hover:text-white sm:block" href="#how-it-works">How it works</a>
            {user ? (
              <Link className="inline-flex min-h-10 items-center gap-2 rounded-xl bg-white px-4 py-2 text-sm font-bold text-ink transition hover:bg-brand-50" href="/dashboard">
                Open workspace <ArrowRightIcon size={16} />
              </Link>
            ) : (
              <a className="inline-flex min-h-10 items-center rounded-xl border border-white/20 px-4 py-2 text-sm font-bold text-white transition hover:bg-white/10" href="#sign-in">Teacher sign in</a>
            )}
          </div>
        </nav>

        <section className="relative mx-auto grid max-w-7xl gap-14 px-5 pb-20 pt-10 sm:px-8 sm:pb-24 lg:grid-cols-[1.08fr_.78fr] lg:items-center lg:px-10 lg:pb-28 lg:pt-16">
          <div className="animate-slide-up">
            <div className="inline-flex items-center gap-2 rounded-full border border-brand-300/25 bg-brand-400/10 px-3 py-1.5 text-xs font-bold text-brand-100">
              <SparkleIcon size={15} /> Smarter assessment, less admin
            </div>
            <h1 className="mt-7 max-w-3xl text-4xl font-black leading-[1.08] tracking-[-0.04em] sm:text-5xl lg:text-6xl">
              Turn answer sheets into <span className="text-brand-300">clear decisions.</span>
            </h1>
            <p className="mt-6 max-w-xl text-base leading-7 text-slate-300 sm:text-lg">
              Create an exam, scan a whole class, and review accurate results in minutes. Markwise keeps every answer traceable, from paper to insight.
            </p>
            <div className="mt-8 flex flex-wrap gap-x-6 gap-y-3 text-sm font-semibold text-slate-200">
              {["Batch sheet scanning", "Question-level grading", "Instant CSV exports"].map((item) => (
                <span className="inline-flex items-center gap-2" key={item}><span className="grid h-5 w-5 place-items-center rounded-full bg-emerald-400/15 text-emerald-300"><CheckIcon size={13} /></span>{item}</span>
              ))}
            </div>

            <div className="mt-12 max-w-xl rounded-2xl border border-white/10 bg-white/[0.07] p-4 backdrop-blur sm:p-5">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-xs font-bold uppercase tracking-[0.15em] text-slate-400">Latest scan batch</p>
                  <p className="mt-1 text-sm font-bold">Biology — Section 10B</p>
                </div>
                <span className="rounded-full bg-emerald-400/15 px-2.5 py-1 text-xs font-bold text-emerald-300">28 processed</span>
              </div>
              <div className="mt-5 grid grid-cols-3 gap-3">
                {[{ label: "Average", value: "78.4%" }, { label: "Highest", value: "96%" }, { label: "Pass rate", value: "89%" }].map((metric) => (
                  <div className="rounded-xl bg-black/15 p-3" key={metric.label}><p className="text-xs text-slate-400">{metric.label}</p><p className="mt-1 text-lg font-black">{metric.value}</p></div>
                ))}
              </div>
            </div>
          </div>

          <div className="animate-slide-up lg:pl-8" id="sign-in" style={{ animationDelay: "100ms" }}>
            <div className="rounded-3xl border border-white/10 bg-white p-6 text-slate-900 shadow-glow sm:p-8">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-sm font-bold text-brand-600">Teacher workspace</p>
                  <h2 className="mt-1 text-2xl font-black tracking-tight">Welcome back</h2>
                  <p className="mt-2 text-sm leading-6 text-slate-500">Sign in to manage exams and scan results.</p>
                </div>
                <span className="grid h-11 w-11 place-items-center rounded-xl bg-brand-50 text-brand-600"><ShieldIcon /></span>
              </div>

              {loading ? (
                <div className="flex min-h-60 items-center justify-center text-brand-600"><Spinner className="h-6 w-6" /><span className="ml-3 text-sm font-semibold text-slate-500">Checking your session…</span></div>
              ) : user ? (
                <div className="mt-8">
                  <Alert tone="success" title={`Signed in as ${user.name}`}>Your workspace is ready.</Alert>
                  <Link className="button-primary mt-5 w-full" href="/dashboard">Continue to dashboard <ArrowRightIcon size={17} /></Link>
                </div>
              ) : (
                <form className="mt-7 space-y-5" onSubmit={handleSubmit}>
                  {error && <Alert>{error}</Alert>}
                  <div>
                    <label className="field-label" htmlFor="email">Email address</label>
                    <div className="relative"><MailIcon className="pointer-events-none absolute left-3.5 top-3.5 text-slate-400" size={18} /><input autoComplete="email" className="text-field pl-11" id="email" onChange={(event) => setEmail(event.target.value)} placeholder="you@school.edu" required type="email" value={email} /></div>
                  </div>
                  <div>
                    <div className="mb-2 flex items-center justify-between"><label className="text-sm font-semibold text-slate-700" htmlFor="password">Password</label></div>
                    <div className="relative"><LockIcon className="pointer-events-none absolute left-3.5 top-3.5 text-slate-400" size={18} /><input autoComplete="current-password" className="text-field pl-11" id="password" minLength={6} onChange={(event) => setPassword(event.target.value)} required type="password" value={password} /></div>
                  </div>
                  <button className="button-primary w-full" disabled={submitting} type="submit">{submitting ? <><Spinner /> Signing in…</> : <>Sign in securely <ArrowRightIcon size={17} /></>}</button>
                  <p className="text-center text-xs leading-5 text-slate-400">Access is managed by your school administrator.</p>
                  {allowDemo && (
                    <div className="border-t border-slate-200 pt-4">
                      <button className="button-secondary w-full" onClick={handleDemo} type="button">Continue in local demo <ArrowRightIcon size={17} /></button>
                      <p className="mt-3 text-center text-xs leading-5 text-slate-400">Demo mode unlocks the UI against a backend running with AUTH_REQUIRED=false.</p>
                    </div>
                  )}
                </form>
              )}
            </div>
          </div>
        </section>
      </div>

      <section className="mx-auto max-w-7xl px-5 py-16 sm:px-8 sm:py-20 lg:px-10" id="how-it-works">
        <div className="mx-auto max-w-2xl text-center">
          <p className="text-xs font-extrabold uppercase tracking-[0.2em] text-brand-600">One dependable workflow</p>
          <h2 className="mt-3 text-3xl font-black tracking-tight text-slate-950 sm:text-4xl">From exam setup to useful insight</h2>
          <p className="mt-4 text-base leading-7 text-slate-500">Everything a teacher needs, without a maze of screens.</p>
        </div>
        <div className="mt-12 grid gap-5 md:grid-cols-3">
          {[
            { number: "01", title: "Create your exam", description: "Set the question count, then enter, scan, or import your answer key.", icon: <CheckIcon /> },
            { number: "02", title: "Scan the class", description: "Drop images, PDFs, or a ZIP batch and attach student details before processing.", icon: <ScanIcon /> },
            { number: "03", title: "Review and act", description: "See grades, pass rates, and every marked answer, then export the full dataset.", icon: <SparkleIcon /> },
          ].map((step) => (
            <article className="rounded-2xl border border-slate-200 bg-slate-50 p-6 transition hover:-translate-y-1 hover:bg-white hover:shadow-card" key={step.number}>
              <div className="flex items-center justify-between"><span className="grid h-11 w-11 place-items-center rounded-xl bg-brand-600 text-white">{step.icon}</span><span className="text-sm font-black text-slate-300">{step.number}</span></div>
              <h3 className="mt-6 text-lg font-extrabold text-slate-900">{step.title}</h3><p className="mt-2 text-sm leading-6 text-slate-500">{step.description}</p>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
