"use client";

import { Library, Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { ConfirmDialog, Modal } from "@/components/Modal";
import { useToast } from "@/components/Toast";
import { EmptyState, ErrorState, Field, PageHeader, Spinner, TableSkeleton } from "@/components/ui";
import { api, RESERVED_CATEGORIES, type Course } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useAsync } from "@/lib/hooks";

type Reserved = Record<(typeof RESERVED_CATEGORIES)[number], string>;

// Central reservation shares (OBC 27%, SC 15%, ST 7.5%), rounded down per course.
const STANDARD_QUOTAS = { OBC: 0.27, SC: 0.15, ST: 0.075 };

const QUOTA_COLORS: Record<string, string> = {
  OBC: "bg-sky-400 dark:bg-sky-500",
  SC: "bg-violet-400 dark:bg-violet-500",
  ST: "bg-amber-400 dark:bg-amber-500",
};

function reservedOf(course: Course, code: string) {
  return course.quotas.find((q) => q.category_code === code)?.reserved_seats ?? 0;
}

function SeatBar({ course }: { course: Course }) {
  if (course.total_seats === 0) return <span className="text-xs text-slate-400">No seats</span>;
  const parts = [
    { key: "Open", value: course.open_seats, cls: "bg-brand-500" },
    ...RESERVED_CATEGORIES.map((c) => ({ key: c, value: reservedOf(course, c), cls: QUOTA_COLORS[c] })),
  ].filter((p) => p.value > 0);
  return (
    <div
      className="flex h-2 w-40 gap-[2px] overflow-hidden rounded-full"
      role="img"
      aria-label={parts.map((p) => `${p.key} ${p.value}`).join(", ")}
    >
      {parts.map((p) => (
        <div
          key={p.key}
          className={p.cls}
          title={`${p.key}: ${p.value}`}
          style={{ width: `${(p.value / course.total_seats) * 100}%` }}
        />
      ))}
    </div>
  );
}

function CourseForm({
  course,
  onClose,
  onSaved,
}: {
  course: Course | null;
  onClose: () => void;
  onSaved: (c: Course) => void;
}) {
  const [name, setName] = useState(course?.name ?? "");
  const [seats, setSeats] = useState(course ? String(course.total_seats) : "30");
  const [reserved, setReserved] = useState<Reserved>({
    OBC: String(course ? reservedOf(course, "OBC") : 0),
    SC: String(course ? reservedOf(course, "SC") : 0),
    ST: String(course ? reservedOf(course, "ST") : 0),
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const total = Number(seats) || 0;
  const reservedTotal = RESERVED_CATEGORIES.reduce((s, c) => s + (Number(reserved[c]) || 0), 0);
  const open = total - reservedTotal;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    const body = {
      name,
      total_seats: total,
      quotas: RESERVED_CATEGORIES.map((c) => ({
        category_code: c,
        reserved_seats: Number(reserved[c]) || 0,
      })),
    };
    try {
      onSaved(course ? await api.updateCourse(course.id, body) : await api.createCourse(body));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="sm:col-span-2">
          <Field label="Course name" htmlFor="course_name">
            <input
              id="course_name"
              className="input"
              required
              maxLength={120}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Computer Science"
            />
          </Field>
        </div>
        <Field label="Total seats" htmlFor="total_seats">
          <input
            id="total_seats"
            className="input"
            type="number"
            min={0}
            max={10000}
            required
            value={seats}
            onChange={(e) => setSeats(e.target.value)}
          />
        </Field>
      </div>

      <fieldset>
        <legend className="label flex w-full flex-wrap items-baseline justify-between gap-2">
          Reserved seats by category
          <button
            type="button"
            className="text-xs font-medium text-brand-600 hover:underline dark:text-brand-400"
            onClick={() =>
              setReserved({
                OBC: String(Math.floor(total * STANDARD_QUOTAS.OBC)),
                SC: String(Math.floor(total * STANDARD_QUOTAS.SC)),
                ST: String(Math.floor(total * STANDARD_QUOTAS.ST)),
              })
            }
          >
            Apply standard quotas (27% / 15% / 7.5%)
          </button>
        </legend>
        <div className="grid gap-3 sm:grid-cols-3">
          {RESERVED_CATEGORIES.map((c) => (
            <div key={c}>
              <label htmlFor={`q_${c}`} className="mb-1 block text-xs text-slate-500 dark:text-slate-400">
                {c}
              </label>
              <input
                id={`q_${c}`}
                className="input"
                type="number"
                min={0}
                max={10000}
                value={reserved[c]}
                onChange={(e) => setReserved({ ...reserved, [c]: e.target.value })}
              />
            </div>
          ))}
        </div>
      </fieldset>

      <div className={open < 0 ? "alert-error" : "alert-info"}>
        {open < 0 ? (
          <p>
            Reserved seats ({reservedTotal}) exceed total seats ({total}).
          </p>
        ) : (
          <p>
            <strong>{open}</strong> open (merit) seat{open === 1 ? "" : "s"} + {reservedTotal}{" "}
            reserved. Reserved-category students take open seats first when their marks allow,
            so quotas act as a guaranteed minimum.
          </p>
        )}
      </div>

      {error && (
        <p role="alert" className="alert-error">
          {error}
        </p>
      )}

      <div className="flex justify-end gap-2 border-t border-slate-100 pt-4 dark:border-slate-800">
        <button type="button" className="btn-secondary" onClick={onClose} disabled={busy}>
          Cancel
        </button>
        <button type="submit" className="btn-primary" disabled={busy || open < 0}>
          {busy && <Spinner />} {course ? "Save changes" : "Create course"}
        </button>
      </div>
    </form>
  );
}

export default function CoursesPage() {
  const { isAdmin } = useAuth();
  const toast = useToast();
  const { data: courses, error, loading, reload } = useAsync(api.listCourses);
  const [editing, setEditing] = useState<Course | "new" | null>(null);
  const [deleting, setDeleting] = useState<Course | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  const totals = (courses ?? []).reduce(
    (acc, c) => ({ seats: acc.seats + c.total_seats, open: acc.open + c.open_seats }),
    { seats: 0, open: 0 },
  );

  const confirmDelete = async () => {
    if (!deleting) return;
    setDeleteBusy(true);
    try {
      await api.deleteCourse(deleting.id);
      toast.success(`Deleted ${deleting.name}.`);
      setDeleting(null);
      reload();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setDeleteBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Courses"
        subtitle={
          courses
            ? `${courses.length} courses · ${totals.seats} seats (${totals.open} open, ${totals.seats - totals.open} reserved)`
            : "Seat capacity and category reservations"
        }
        actions={
          isAdmin && (
            <button type="button" className="btn-primary" onClick={() => setEditing("new")}>
              <Plus className="h-4 w-4" /> Add course
            </button>
          )
        }
      />

      <div className="card">
        {error && (
          <div className="p-5">
            <ErrorState message={error} onRetry={reload} />
          </div>
        )}
        {!courses && loading && <TableSkeleton cols={6} />}
        {courses && courses.length === 0 && (
          <EmptyState
            icon={Library}
            title="No courses yet"
            description={isAdmin ? "Add a course with its seats and reservation quotas." : undefined}
            action={
              isAdmin && (
                <button type="button" className="btn-primary" onClick={() => setEditing("new")}>
                  <Plus className="h-4 w-4" /> Add course
                </button>
              )
            }
          />
        )}
        {courses && courses.length > 0 && (
          <>
            <div className="relative overflow-x-auto">
              <table className="table">
                <thead>
                  <tr>
                    <th>Course</th>
                    <th className="text-right">Seats</th>
                    <th>Composition</th>
                    <th className="text-right">Open</th>
                    {RESERVED_CATEGORIES.map((c) => (
                      <th key={c} className="text-right">
                        {c}
                      </th>
                    ))}
                    <th className="text-right">Applicants</th>
                    <th className="text-right" title="Applicants per seat">
                      Demand
                    </th>
                    {isAdmin && <th className="w-24"><span className="sr-only">Actions</span></th>}
                  </tr>
                </thead>
                <tbody>
                  {courses.map((c) => (
                    <tr key={c.id}>
                      <td className="font-medium text-slate-900 dark:text-slate-100">{c.name}</td>
                      <td className="text-right tabular-nums">{c.total_seats}</td>
                      <td>
                        <SeatBar course={c} />
                      </td>
                      <td className="text-right tabular-nums">{c.open_seats}</td>
                      {RESERVED_CATEGORIES.map((code) => (
                        <td key={code} className="text-right tabular-nums">
                          {reservedOf(c, code)}
                        </td>
                      ))}
                      <td className="text-right tabular-nums">{c.applicants}</td>
                      <td className="text-right tabular-nums">
                        {c.total_seats ? `${(c.applicants / c.total_seats).toFixed(1)}×` : "—"}
                      </td>
                      {isAdmin && (
                        <td>
                          <div className="flex justify-end gap-1">
                            <button
                              type="button"
                              className="btn-icon"
                              onClick={() => setEditing(c)}
                              aria-label={`Edit ${c.name}`}
                            >
                              <Pencil className="h-4 w-4" />
                            </button>
                            <button
                              type="button"
                              className="btn-icon hover:!text-red-600"
                              onClick={() => setDeleting(c)}
                              aria-label={`Delete ${c.name}`}
                            >
                              <Trash2 className="h-4 w-4" />
                            </button>
                          </div>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex flex-wrap gap-x-4 gap-y-1 border-t border-slate-100 px-5 py-3 text-xs text-slate-500 dark:border-slate-800 dark:text-slate-400">
              <span className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-sm bg-brand-500" /> Open (merit)
              </span>
              {RESERVED_CATEGORIES.map((c) => (
                <span key={c} className="flex items-center gap-1.5">
                  <span className={`h-2 w-2 rounded-sm ${QUOTA_COLORS[c]}`} /> {c} reserved
                </span>
              ))}
            </div>
          </>
        )}
      </div>

      <Modal
        open={editing !== null}
        onClose={() => setEditing(null)}
        title={editing === "new" ? "Add course" : "Edit course"}
        description="Re-run the allocation afterwards to apply changes."
      >
        {editing !== null && (
          <CourseForm
            key={editing === "new" ? "new" : editing.id}
            course={editing === "new" ? null : editing}
            onClose={() => setEditing(null)}
            onSaved={(c) => {
              toast.success(editing === "new" ? `Created ${c.name}.` : `Saved ${c.name}.`);
              setEditing(null);
              reload();
            }}
          />
        )}
      </Modal>

      <ConfirmDialog
        open={deleting !== null}
        title="Delete course?"
        message={
          deleting && (
            <>
              <strong>{deleting.name}</strong> will be removed. Courses that students list as a
              preference can&apos;t be deleted until those preferences are changed.
            </>
          )
        }
        busy={deleteBusy}
        onConfirm={confirmDelete}
        onClose={() => setDeleting(null)}
      />
    </div>
  );
}
