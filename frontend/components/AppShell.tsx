"use client";

import {
  Bot,
  GraduationCap,
  LayoutDashboard,
  Library,
  LogOut,
  Menu,
  RotateCcw,
  Shuffle,
  Users,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useMeta } from "@/lib/hooks";
import { ConfirmDialog } from "./Modal";
import ThemeToggle from "./ThemeToggle";
import { useToast } from "./Toast";
import { cx, Spinner } from "./ui";

const NAV = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/students", label: "Students", icon: Users },
  { href: "/courses", label: "Courses", icon: Library },
  { href: "/allocation", label: "Allocation", icon: Shuffle },
  { href: "/assistant", label: "AI Assistant", icon: Bot },
];

const PUBLIC_PATHS = ["/login"];

function Brand() {
  return (
    <Link href="/" className="flex items-center gap-2.5">
      <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-600 text-white shadow-sm">
        <GraduationCap className="h-5 w-5" aria-hidden="true" />
      </span>
      <span className="leading-tight">
        <span className="block text-sm font-semibold text-slate-900 dark:text-white">
          CourseAlloc
        </span>
        <span className="block text-xs text-slate-500 dark:text-slate-400">Seat allocation</span>
      </span>
    </Link>
  );
}

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <nav className="flex flex-col gap-1" aria-label="Main">
      {NAV.map(({ href, label, icon: Icon }) => {
        const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={cx(
              "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
              active
                ? "bg-brand-50 text-brand-700 dark:bg-brand-950 dark:text-brand-300"
                : "text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white",
            )}
          >
            <Icon className="h-4 w-4" aria-hidden="true" />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}

function UserPanel() {
  const { user, logout } = useAuth();
  const router = useRouter();
  if (!user) return null;
  return (
    <div className="flex items-center gap-3 rounded-lg border border-slate-200 p-3 dark:border-slate-800">
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-100 text-sm font-semibold text-slate-700 dark:bg-slate-800 dark:text-slate-200">
        {user.full_name.slice(0, 1).toUpperCase()}
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-slate-900 dark:text-white">
          {user.full_name}
        </p>
        <p className="truncate text-xs text-slate-500 dark:text-slate-400">
          <span className={user.role === "admin" ? "text-brand-600 dark:text-brand-400" : ""}>
            {user.role === "admin" ? "Admin" : "Viewer"}
          </span>{" "}
          · {user.email}
        </p>
      </div>
      <button
        type="button"
        className="btn-icon"
        onClick={() => {
          logout();
          router.replace("/login");
        }}
        aria-label="Sign out"
        title="Sign out"
      >
        <LogOut className="h-4 w-4" />
      </button>
    </div>
  );
}

function DemoBanner() {
  const { data: meta } = useMeta();
  const { isAdmin } = useAuth();
  const toast = useToast();
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  if (!meta?.demo_mode) return null;

  const reset = async () => {
    setBusy(true);
    try {
      await api.resetDemo();
      toast.success("Demo data restored. Reloading…");
      setTimeout(() => window.location.reload(), 600);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Reset failed");
      setBusy(false);
      setConfirming(false);
    }
  };

  return (
    <div className="border-b border-brand-100 bg-brand-50 px-4 py-2 text-sm text-brand-800 dark:border-brand-900 dark:bg-brand-950/60 dark:text-brand-200 sm:px-6 lg:px-8">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-2">
        <p>
          <span className="font-semibold">Live demo.</span> Explore freely — sample data can be
          restored at any time.
        </p>
        {isAdmin && (
          <button
            type="button"
            className="inline-flex items-center gap-1.5 font-medium underline-offset-2 hover:underline"
            onClick={() => setConfirming(true)}
          >
            <RotateCcw className="h-3.5 w-3.5" /> Reset demo data
          </button>
        )}
      </div>
      <ConfirmDialog
        open={confirming}
        title="Reset demo data?"
        message="This replaces all courses and students with the sample dataset and re-runs the allocation."
        confirmLabel="Reset data"
        busy={busy}
        onConfirm={reset}
        onClose={() => setConfirming(false)}
      />
    </div>
  );
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const { status } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const isPublic = PUBLIC_PATHS.includes(pathname);

  useEffect(() => {
    if (status === "anonymous" && !isPublic) {
      const next = pathname && pathname !== "/" ? `?next=${encodeURIComponent(pathname)}` : "";
      router.replace(`/login${next}`);
    }
  }, [status, isPublic, pathname, router]);

  if (isPublic) return <>{children}</>;

  if (status !== "authenticated") {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner className="h-6 w-6 text-brand-600" />
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 flex-col border-r border-slate-200 bg-white px-4 py-5 dark:border-slate-800 dark:bg-slate-900 lg:flex">
        <div className="flex items-center justify-between px-1">
          <Brand />
          <ThemeToggle />
        </div>
        <div className="mt-8 flex-1">
          <NavLinks />
        </div>
        <UserPanel />
      </aside>

      {/* Mobile top bar */}
      <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-slate-200 bg-white/90 px-4 backdrop-blur dark:border-slate-800 dark:bg-slate-900/90 lg:hidden">
        <Brand />
        <div className="flex items-center gap-1">
          <ThemeToggle />
          <button
            type="button"
            className="btn-icon"
            onClick={() => setDrawerOpen(true)}
            aria-label="Open menu"
          >
            <Menu className="h-5 w-5" />
          </button>
        </div>
      </header>

      {/* Mobile drawer */}
      {drawerOpen && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true">
          <div
            className="absolute inset-0 animate-fade-in bg-slate-950/50 backdrop-blur-sm"
            onClick={() => setDrawerOpen(false)}
          />
          <div className="absolute inset-y-0 right-0 flex w-72 max-w-[85%] animate-fade-in flex-col bg-white px-4 py-5 shadow-xl dark:bg-slate-900">
            <div className="flex items-center justify-between px-1">
              <Brand />
              <button
                type="button"
                className="btn-icon"
                onClick={() => setDrawerOpen(false)}
                aria-label="Close menu"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="mt-8 flex-1">
              <NavLinks onNavigate={() => setDrawerOpen(false)} />
            </div>
            <UserPanel />
          </div>
        </div>
      )}

      <div className="lg:pl-64">
        <DemoBanner />
        <main className="mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
          {children}
        </main>
      </div>
    </div>
  );
}
