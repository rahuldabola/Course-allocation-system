"use client";

import { ChevronDown, Download, History, Info, Play, Search, UserX } from "lucide-react";
import { useMemo, useState } from "react";
import { useToast } from "@/components/Toast";
import {
  CategoryBadge,
  cx,
  EmptyState,
  ErrorState,
  PageHeader,
  RankBadge,
  SeatBadge,
  Spinner,
  TableSkeleton,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime, pct, timeAgo } from "@/lib/format";
import { useAsync } from "@/lib/hooks";

type Tab = "allocated" | "unallocated" | "history";

function HowItWorks() {
  const [open, setOpen] = useState(false);
  return (
    <div className="card">
      <button
        type="button"
        className="flex w-full items-center justify-between gap-3 px-5 py-4 text-left sm:px-6"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <span className="flex items-center gap-2 text-sm font-medium text-slate-900 dark:text-slate-100">
          <Info className="h-4 w-4 text-brand-600 dark:text-brand-400" /> How the allocation works
        </span>
        <ChevronDown className={cx("h-4 w-4 text-slate-400 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="grid gap-6 border-t border-slate-100 px-5 py-5 text-sm text-slate-600 dark:border-slate-800 dark:text-slate-300 sm:px-6 md:grid-cols-3">
          <div>
            <p className="font-medium text-slate-900 dark:text-slate-100">1. Merit order</p>
            <p className="mt-1">
              Students are ranked by marks. Ties go to the earlier application date, then to
              the earlier registration, so every run is deterministic.
            </p>
          </div>
          <div>
            <p className="font-medium text-slate-900 dark:text-slate-100">2. Preferences in order</p>
            <p className="mt-1">
              Each student, in merit order, gets the first of their (up to three) preferences
              that still has a seat they&apos;re eligible for. One seat per student.
            </p>
          </div>
          <div>
            <p className="font-medium text-slate-900 dark:text-slate-100">3. Reservation as a floor</p>
            <p className="mt-1">
              Open seats are pure merit. OBC/SC/ST students take an open seat when available,
              otherwise a reserved seat of their own category, so quotas are a guaranteed
              minimum, not a cap.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

export default function AllocationPage() {
  const { isAdmin } = useAuth();
  const toast = useToast();
  const [tab, setTab] = useState<Tab>("allocated");
  const [courseFilter, setCourseFilter] = useState("");
  const [search, setSearch] = useState("");
  const [running, setRunning] = useState(false);

  const allocations = useAsync(() => api.listAllocations());
  const unallocated = useAsync(api.listUnallocated);
  const runs = useAsync(() => api.listRuns(20));
  const courses = useAsync(api.listCourses);

  const lastRun = runs.data?.[0];

  const reloadAll = () => {
    allocations.reload();
    unallocated.reload();
    runs.reload();
  };

  const run = async () => {
    setRunning(true);
    try {
      const res = await api.runAllocation();
      toast.success(`Allocated ${res.allocated} of ${res.total_students} students.`);
      reloadAll();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Allocation failed");
    } finally {
      setRunning(false);
    }
  };

  const exportCsv = () =>
    api.exportAllocations().catch((e: Error) => toast.error(e.message || "Export failed"));

  const needle = search.trim().toLowerCase();
  const filteredAllocations = useMemo(
    () =>
      (allocations.data ?? []).filter(
        (a) =>
          (!courseFilter || String(a.course_id) === courseFilter) &&
          (!needle ||
            a.student_name.toLowerCase().includes(needle) ||
            a.roll_no.toLowerCase().includes(needle)),
      ),
    [allocations.data, courseFilter, needle],
  );
  const filteredUnallocated = useMemo(
    () =>
      (unallocated.data ?? []).filter(
        (s) =>
          !needle ||
          s.student_name.toLowerCase().includes(needle) ||
          s.roll_no.toLowerCase().includes(needle),
      ),
    [unallocated.data, needle],
  );

  const tabs: { id: Tab; label: string; count?: number }[] = [
    { id: "allocated", label: "Allocated", count: allocations.data?.length },
    { id: "unallocated", label: "Unallocated", count: unallocated.data?.length },
    { id: "history", label: "Run history", count: runs.data?.length },
  ];

  const current = tab === "allocated" ? allocations : tab === "unallocated" ? unallocated : runs;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Allocation"
        subtitle={
          lastRun ? (
            <span title={formatDateTime(lastRun.run_at)}>
              Last run {timeAgo(lastRun.run_at)}: {lastRun.allocated} of {lastRun.total_students}{" "}
              students placed (
              {pct(lastRun.total_students ? lastRun.allocated / lastRun.total_students : 0)})
            </span>
          ) : (
            "Run the merit + reservation engine and review the results."
          )
        }
        actions={
          <>
            <button type="button" className="btn-secondary" onClick={exportCsv}>
              <Download className="h-4 w-4" /> Export CSV
            </button>
            {isAdmin && (
              <button type="button" className="btn-primary" onClick={run} disabled={running}>
                {running ? <Spinner /> : <Play className="h-4 w-4" />} Run allocation
              </button>
            )}
          </>
        }
      />

      <HowItWorks />

      <div className="card">
        <div className="border-b border-slate-100 px-5 pt-4 dark:border-slate-800 sm:px-6">
          <nav className="-mb-px flex gap-5 overflow-x-auto sm:gap-6" aria-label="Allocation views" role="tablist">
            {tabs.map((t) => (
              <button
                key={t.id}
                type="button"
                role="tab"
                aria-selected={tab === t.id}
                className={cx("tab", tab === t.id && "tab-active")}
                onClick={() => setTab(t.id)}
              >
                {t.label}
                {t.count !== undefined && (
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                    {t.count}
                  </span>
                )}
              </button>
            ))}
          </nav>
        </div>

        {tab !== "history" && (
          <div className="flex flex-col gap-3 border-b border-slate-100 px-5 py-3 dark:border-slate-800 sm:flex-row sm:px-6">
            <div className="relative flex-1 sm:max-w-xs">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <input
                type="search"
                className="input pl-9"
                placeholder="Search name or roll no…"
                aria-label="Search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            {tab === "allocated" && (
              <select
                className="input sm:w-56"
                aria-label="Filter by course"
                value={courseFilter}
                onChange={(e) => setCourseFilter(e.target.value)}
              >
                <option value="">All courses</option>
                {(courses.data ?? []).map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            )}
          </div>
        )}

        {current.error && (
          <div className="p-5">
            <ErrorState message={current.error} onRetry={current.reload} />
          </div>
        )}
        {!current.data && current.loading && <TableSkeleton cols={5} />}

        {tab === "allocated" && allocations.data && (
          filteredAllocations.length === 0 ? (
            <EmptyState
              title={allocations.data.length ? "No matches" : "No allocations yet"}
              description={
                allocations.data.length
                  ? "Try another search or course."
                  : isAdmin
                    ? "Run the allocation to place students."
                    : "An admin hasn't run the allocation yet."
              }
            />
          ) : (
            <div className="relative overflow-x-auto">
              <table className="table">
                <thead>
                  <tr>
                    <th>Student</th>
                    <th className="text-right">Marks</th>
                    <th>Category</th>
                    <th>Course</th>
                    <th>Seat</th>
                    <th>Preference</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredAllocations.map((a) => (
                    <tr key={a.student_id}>
                      <td>
                        <div className="font-medium text-slate-900 dark:text-slate-100">{a.student_name}</div>
                        <div className="font-mono text-xs text-slate-500">{a.roll_no}</div>
                      </td>
                      <td className="text-right font-medium tabular-nums">{a.marks.toFixed(1)}</td>
                      <td><CategoryBadge code={a.category_code} /></td>
                      <td className="text-slate-900 dark:text-slate-100">{a.course_name}</td>
                      <td><SeatBadge type={a.seat_type} /></td>
                      <td><RankBadge rank={a.preference_rank} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        )}

        {tab === "unallocated" && unallocated.data && (
          filteredUnallocated.length === 0 ? (
            <EmptyState
              icon={UserX}
              title={unallocated.data.length ? "No matches" : "Everyone has a seat"}
              description={unallocated.data.length ? "Try another search." : "No student is left without a seat."}
            />
          ) : (
            <div className="relative overflow-x-auto">
              <table className="table">
                <thead>
                  <tr>
                    <th>Student</th>
                    <th className="text-right">Marks</th>
                    <th>Category</th>
                    <th>Preferences (all full)</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredUnallocated.map((s) => (
                    <tr key={s.student_id}>
                      <td>
                        <div className="font-medium text-slate-900 dark:text-slate-100">{s.student_name}</div>
                        <div className="font-mono text-xs text-slate-500">{s.roll_no}</div>
                      </td>
                      <td className="text-right font-medium tabular-nums">{s.marks.toFixed(1)}</td>
                      <td><CategoryBadge code={s.category_code} /></td>
                      <td>
                        <ol className="flex flex-wrap gap-1">
                          {s.preferences.map((p, i) => (
                            <li key={p} className="badge-gray">
                              <span className="text-slate-400">{i + 1}.</span>
                              {p}
                            </li>
                          ))}
                          {s.preferences.length === 0 && (
                            <li className="text-xs text-slate-400">No preferences listed</li>
                          )}
                        </ol>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        )}

        {tab === "history" && runs.data && (
          runs.data.length === 0 ? (
            <EmptyState icon={History} title="No runs yet" />
          ) : (
            <div className="relative overflow-x-auto">
              <table className="table">
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Triggered by</th>
                    <th className="text-right">Students</th>
                    <th className="text-right">Allocated</th>
                    <th className="text-right">Rate</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.data.map((r) => (
                    <tr key={r.id}>
                      <td>
                        <div className="text-slate-900 dark:text-slate-100">{formatDateTime(r.run_at)}</div>
                        <div className="text-xs text-slate-500">{timeAgo(r.run_at)}</div>
                      </td>
                      <td>{r.triggered_by ?? "—"}</td>
                      <td className="text-right tabular-nums">{r.total_students}</td>
                      <td className="text-right tabular-nums">{r.allocated}</td>
                      <td className="text-right tabular-nums">
                        {pct(r.total_students ? r.allocated / r.total_students : 0)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        )}
      </div>
    </div>
  );
}
