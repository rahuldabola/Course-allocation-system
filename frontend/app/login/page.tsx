"use client";

import {
  ArrowRight,
  Bot,
  Eye,
  GraduationCap,
  Scale,
  ShieldCheck,
  UserCog,
  type LucideIcon,
} from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import ThemeToggle from "@/components/ThemeToggle";
import { Field, Spinner } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { useMeta } from "@/lib/hooks";

const FEATURES: { icon: LucideIcon; title: string; text: string }[] = [
  {
    icon: Scale,
    title: "Merit + reservation engine",
    text: "Seats go by marks, with category quotas guaranteed as a floor, never a ceiling.",
  },
  {
    icon: Bot,
    title: "AI assistant",
    text: "Ask questions in plain English; answers come from validated, read-only SQL.",
  },
  {
    icon: ShieldCheck,
    title: "Role-based access",
    text: "Admins manage data and run allocations; viewers get read-only analytics.",
  },
];

function safeNext(next: string | null): string {
  // Only allow same-site relative paths (avoid open redirects).
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/";
}

function LoginForm() {
  const { login, status } = useAuth();
  const { data: meta } = useMeta();
  const router = useRouter();
  const params = useSearchParams();
  const next = safeNext(params.get("next"));

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    if (status === "authenticated") router.replace(next);
  }, [status, next, router]);

  const signIn = async (e: string, p: string, key: string) => {
    setError(null);
    setBusy(key);
    try {
      await login(e, p);
      router.replace(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed");
      setBusy(null);
    }
  };

  return (
    <div className="w-full max-w-sm">
      <div className="mb-8 lg:hidden">
        <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-600 text-white">
          <GraduationCap className="h-5 w-5" />
        </span>
      </div>
      <h1 className="text-2xl font-semibold tracking-tight text-slate-900 dark:text-white">
        Sign in to CourseAlloc
      </h1>
      <p className="mt-1.5 text-sm text-slate-500 dark:text-slate-400">
        Manage students, courses and seat allocation.
      </p>

      {meta?.demo_mode && meta.demo_accounts.length > 0 && (
        <div className="mt-8 rounded-xl border border-brand-200 bg-brand-50/70 p-4 dark:border-brand-900 dark:bg-brand-950/40">
          <p className="text-sm font-semibold text-brand-900 dark:text-brand-100">
            Try the live demo
          </p>
          <p className="mt-0.5 text-xs text-brand-800/80 dark:text-brand-200/80">
            One click, no sign-up. Demo data can be reset at any time.
          </p>
          <div className="mt-3 grid gap-2">
            {meta.demo_accounts.map((acct) => {
              const Icon = acct.role === "admin" ? UserCog : Eye;
              return (
                <button
                  key={acct.email}
                  type="button"
                  disabled={busy !== null}
                  onClick={() => signIn(acct.email, acct.password, acct.email)}
                  className="group flex items-center gap-3 rounded-lg border border-brand-200 bg-white px-3 py-2.5 text-left transition hover:border-brand-400 hover:shadow-sm disabled:opacity-60 dark:border-brand-900 dark:bg-slate-900 dark:hover:border-brand-600"
                >
                  <Icon className="h-4 w-4 text-brand-600 dark:text-brand-400" />
                  <span className="flex-1">
                    <span className="block text-sm font-medium text-slate-900 dark:text-white">
                      Continue as {acct.role === "admin" ? "Admin" : "Viewer"}
                    </span>
                    <span className="block text-xs text-slate-500 dark:text-slate-400">
                      {acct.role === "admin" ? "Full access" : "Read-only + AI assistant"} ·{" "}
                      {acct.email}
                    </span>
                  </span>
                  {busy === acct.email ? (
                    <Spinner className="h-4 w-4 text-brand-600" />
                  ) : (
                    <ArrowRight className="h-4 w-4 text-slate-400 transition group-hover:translate-x-0.5 group-hover:text-brand-600" />
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}

      <form
        className="mt-8 space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          void signIn(email, password, "form");
        }}
      >
        {meta?.demo_mode && (
          <div className="relative text-center text-xs text-slate-400">
            <span className="relative z-10 bg-slate-50 px-2 dark:bg-slate-950">
              or sign in with email
            </span>
            <span className="absolute inset-x-0 top-1/2 -z-0 border-t border-slate-200 dark:border-slate-800" />
          </div>
        )}
        <Field label="Email" htmlFor="email">
          <input
            id="email"
            type="email"
            autoComplete="username"
            required
            className="input"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </Field>
        <Field label="Password" htmlFor="password">
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            required
            className="input"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>
        {error && (
          <p role="alert" className="text-sm text-red-600 dark:text-red-400">
            {error}
          </p>
        )}
        <button type="submit" className="btn-primary w-full" disabled={busy !== null}>
          {busy === "form" && <Spinner />} Sign in
        </button>
      </form>
    </div>
  );
}

export default function LoginPage() {
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <section className="relative hidden flex-col justify-between overflow-hidden bg-brand-950 p-12 text-white lg:flex">
        <div
          aria-hidden="true"
          className="absolute inset-0 opacity-40"
          style={{
            backgroundImage:
              "radial-gradient(circle at 20% 20%, rgba(99,102,241,.55), transparent 45%), radial-gradient(circle at 80% 70%, rgba(14,165,233,.35), transparent 40%)",
          }}
        />
        <div className="relative flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-white/10 ring-1 ring-white/20">
            <GraduationCap className="h-5 w-5" />
          </span>
          <span className="text-lg font-semibold">CourseAlloc</span>
        </div>
        <div className="relative max-w-md">
          <h2 className="text-3xl font-semibold leading-tight tracking-tight">
            Fair, explainable course allocation, from applications to answers.
          </h2>
          <ul className="mt-10 space-y-6">
            {FEATURES.map(({ icon: Icon, title, text }) => (
              <li key={title} className="flex gap-4">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white/10 ring-1 ring-white/15">
                  <Icon className="h-4 w-4" />
                </span>
                <span>
                  <span className="block font-medium">{title}</span>
                  <span className="mt-0.5 block text-sm text-brand-100/80">{text}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
        <p className="relative text-xs text-brand-200/70">
          FastAPI · PostgreSQL · Next.js · Gemini
        </p>
      </section>
      <section className="relative flex items-center justify-center px-6 py-12">
        <div className="absolute right-4 top-4">
          <ThemeToggle />
        </div>
        <Suspense fallback={<Spinner className="h-6 w-6 text-brand-600" />}>
          <LoginForm />
        </Suspense>
      </section>
    </div>
  );
}
