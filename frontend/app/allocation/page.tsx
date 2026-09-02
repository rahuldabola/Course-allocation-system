"use client";
import { useEffect, useState } from "react";
import { api, Allocation } from "@/lib/api";

export default function AllocationPage() {
  const [rows, setRows] = useState<Allocation[]>([]);
  const [summary, setSummary] = useState<{ total: number; allocated: number; unallocated: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = () => api.listAllocations().then(setRows).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);

  async function run() {
    setBusy(true); setError("");
    try {
      const r = await api.runAllocation();
      setRows(r.allocations);
      setSummary({ total: r.total_students, allocated: r.allocated, unallocated: r.unallocated });
    } catch (e: any) { setError(e.message); } finally { setBusy(false); }
  }

  const badge = (rank: number) =>
    rank === 1 ? "badge-success"
      : rank === 2 ? "badge-warning" : "badge-danger";

  const successRate = summary ? Math.round((summary.allocated / summary.total) * 100) : 0;

  return (
    <div className="space-y-8 animate-fade-in">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold">✨ Course Allocation</h1>
          <p className="text-slate-600 text-sm mt-1">Run the allocation algorithm and view results</p>
        </div>
        <button className="btn" onClick={run} disabled={busy}>
          {busy ? "⏳ Processing…" : "▶️ Run Allocation"}
        </button>
      </div>

      {error && <div className="error-box">{error}</div>}

      {summary && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          <div className="stat-card">
            <p className="label">Total Students</p>
            <p className="text-3xl font-bold text-slate-800 mt-2">{summary.total}</p>
          </div>
          <div className="stat-card-gradient">
            <p className="label text-brand-700">Successfully Allocated</p>
            <p className="text-3xl font-bold text-emerald-600 mt-2">{summary.allocated}</p>
            <p className="text-xs text-slate-600 mt-3">
              <span className="font-semibold text-brand">{successRate}%</span> success rate
            </p>
          </div>
          <div className="stat-card">
            <p className="label">Pending Allocation</p>
            <p className="text-3xl font-bold text-red-500 mt-2">{summary.unallocated}</p>
          </div>
        </div>
      )}

      <div className="card overflow-x-auto">
        <div className="section-header mb-6">
          <div>
            <h2 className="text-lg font-semibold">Allocation Results</h2>
            <p className="text-sm text-slate-500 mt-1">{rows.length} allocation{rows.length !== 1 ? "s" : ""}</p>
          </div>
        </div>
        <table className="w-full">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50">
              <th className="th">Student</th>
              <th className="th">Marks</th>
              <th className="th">Category</th>
              <th className="th">Allocated Course</th>
              <th className="th">Seat Type</th>
              <th className="th">Preference Rank</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((a) => (
              <tr key={a.student_id} className="tr-hover">
                <td className="td">
                  <div className="font-semibold text-slate-800">{a.student_name}</div>
                  <div className="font-mono text-xs text-slate-500 mt-0.5">{a.roll_no}</div>
                </td>
                <td className="td">
                  <span className="badge badge-primary">{a.marks}</span>
                </td>
                <td className="td">
                  <span className={`badge ${a.category_code === "General" ? "badge-info" : "badge-warning"}`}>
                    {a.category_code}
                  </span>
                </td>
                <td className="td font-semibold text-slate-800">{a.course_name}</td>
                <td className="td">
                  <span className={`badge ${a.seat_type === "open" ? "badge-info" : "badge-primary"}`}>
                    {a.seat_type === "open" ? "General" : a.seat_type.toUpperCase()}
                  </span>
                </td>
                <td className="td">
                  <span className={`badge ${badge(a.preference_rank)}`}>
                    #{a.preference_rank} choice
                  </span>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td className="td text-slate-400 py-8 text-center" colSpan={6}>No allocations yet. Click &quot;Run Allocation&quot; to start.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
