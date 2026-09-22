"use client";

import { Armchair, Library, Play, RefreshCw, TrendingDown, UserCheck, Users } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { CategoryChart, PreferenceBar, RejectionChart, SeatUtilizationChart } from "@/components/charts";
import { useToast } from "@/components/Toast";
import { EmptyState, ErrorState, PageHeader, Spinner, StatCard } from "@/components/ui";
import { api, type DashboardStats } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime, pct, timeAgo } from "@/lib/format";
import { useAsync } from "@/lib/hooks";

function DashboardSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Loading dashboard">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i} className="card card-body space-y-3">
            <div className="skeleton h-4 w-24" />
            <div className="skeleton h-8 w-16" />
            <div className="skeleton h-4 w-32" />
          </div>
        ))}
      </div>
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <div className="card h-80 p-6"><div className="skeleton h-full w-full" /></div>
        <div className="card h-80 p-6"><div className="skeleton h-full w-full" /></div>
      </div>
    </div>
  );
}

function CourseTable({ stats }: { stats: DashboardStats }) {
  return (
    <div className="relative overflow-x-auto">
      <table className="table">
        <thead>
          <tr>
            <th>Course</th>
            <th className="text-right">Seats</th>
            <th className="text-right">Applicants</th>
            <th className="text-right">Allocated</th>
            <th className="text-right">Rejection rate</th>
          </tr>
        </thead>
        <tbody>
          {stats.course_stats.map((c) => {
            return (
              <tr key={c.course_id}>
                <td className="font-medium text-slate-900 dark:text-slate-100">{c.course_name}</td>
                <td className="text-right tabular-nums">{c.total_seats}</td>
                <td className="text-right tabular-nums">{c.applicants}</td>
                <td className="text-right tabular-nums">{c.allocated}</td>
                <td className="text-right tabular-nums">{pct(c.rejection_rate, 1)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function DashboardPage() {
  const { isAdmin } = useAuth();
  const toast = useToast();
  const { data: stats, error, loading, reload } = useAsync(api.stats);
  const [running, setRunning] = useState(false);

  const runAllocation = async () => {
    setRunning(true);
    try {
      const res = await api.runAllocation();
      toast.success(`Allocated ${res.allocated} of ${res.total_students} students.`);
      reload();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Allocation failed");
    } finally {
      setRunning(false);
    }
  };

  const lastRun = stats?.last_run;
  const hasCourses = (stats?.total_courses ?? 0) > 0;
  const worst = stats?.course_stats.find((c) => c.course_name === stats.highest_rejection_course);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        subtitle={
          lastRun ? (
            <span title={formatDateTime(lastRun.run_at)}>
              Last allocation {timeAgo(lastRun.run_at)}
              {lastRun.triggered_by ? ` by ${lastRun.triggered_by}` : ""}
            </span>
          ) : (
            "Allocation overview and analytics"
          )
        }
        actions={
          <>
            <button type="button" className="btn-secondary" onClick={reload} disabled={loading}>
              <RefreshCw className={loading && stats ? "h-4 w-4 animate-spin" : "h-4 w-4"} /> Refresh
            </button>
            {isAdmin && hasCourses && (
              <button type="button" className="btn-primary" onClick={runAllocation} disabled={running}>
                {running ? <Spinner /> : <Play className="h-4 w-4" />} Run allocation
              </button>
            )}
          </>
        }
      />

      {error && <ErrorState message={error} onRetry={reload} />}
      {!stats && loading && <DashboardSkeleton />}

      {stats && !hasCourses && (
        <div className="card">
          <EmptyState
            icon={Library}
            title="No courses yet"
            description="Create courses with seat quotas, register students with their preferences, then run the allocation."
            action={
              <Link href="/courses" className="btn-primary">
                Set up courses
              </Link>
            }
          />
        </div>
      )}

      {stats && hasCourses && (
        <div className={loading ? "space-y-6 opacity-60 transition-opacity" : "space-y-6"}>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard
              label="Students"
              value={stats.total_students.toLocaleString()}
              detail={`${stats.total_courses} courses · ${stats.total_seats} seats`}
              icon={Users}
            />
            <StatCard
              label="Allocated"
              value={stats.total_allocated.toLocaleString()}
              detail={`${pct(stats.allocation_rate)} of students placed`}
              icon={UserCheck}
              tone="green"
            />
            <StatCard
              label="Seats filled"
              value={pct(stats.seat_fill_rate)}
              detail={`${stats.total_unallocated} students without a seat`}
              icon={Armchair}
              tone="sky"
            />
            <StatCard
              label="Highest rejection rate"
              value={worst ? pct(worst.rejection_rate, 1) : "—"}
              detail={worst ? `${worst.course_name} (${worst.applicants} applicants)` : "No applicants yet"}
              icon={TrendingDown}
              tone="amber"
            />
          </div>

          {!lastRun && (
            <div className="alert-info">
              <p>
                No allocation has been run yet.{" "}
                {isAdmin ? "Use “Run allocation” to place students." : "Ask an admin to run it."}
              </p>
            </div>
          )}

          <div className="card">
            <div className="card-header">
              <div>
                <h2 className="card-title">Preference satisfaction</h2>
                <p className="card-subtitle">Which choice each student received</p>
              </div>
            </div>
            <div className="card-body">
              <PreferenceBar stats={stats.preference_stats} unallocated={stats.total_unallocated} />
            </div>
          </div>

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
            <div className="card">
              <div className="card-header">
                <div>
                  <h2 className="card-title">Seat utilisation</h2>
                  <p className="card-subtitle">Allocated vs free seats per course</p>
                </div>
              </div>
              <div className="card-body">
                <SeatUtilizationChart courses={stats.course_stats} />
              </div>
            </div>
            <div className="card">
              <div className="card-header">
                <div>
                  <h2 className="card-title">Rejection rate by course</h2>
                  <p className="card-subtitle">
                    Applicants not placed in the course · highest highlighted
                  </p>
                </div>
              </div>
              <div className="card-body">
                <RejectionChart courses={stats.course_stats} />
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-5">
            <div className="card xl:col-span-2">
              <div className="card-header">
                <div>
                  <h2 className="card-title">Category-wise allocation</h2>
                  <p className="card-subtitle">Applicants and placements per category</p>
                </div>
              </div>
              <div className="card-body">
                <CategoryChart stats={stats.category_stats} />
              </div>
            </div>
            <div className="card xl:col-span-3">
              <div className="card-header">
                <div>
                  <h2 className="card-title">Course breakdown</h2>
                  <p className="card-subtitle">Demand, placements and rejection per course</p>
                </div>
              </div>
              <CourseTable stats={stats} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
