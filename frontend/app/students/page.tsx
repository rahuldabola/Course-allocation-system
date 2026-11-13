"use client";

import {
  ChevronLeft,
  ChevronRight,
  Download,
  FileUp,
  Pencil,
  Plus,
  Search,
  Trash2,
  Users,
} from "lucide-react";
import { useState } from "react";
import { ConfirmDialog, Modal } from "@/components/Modal";
import { useToast } from "@/components/Toast";
import {
  CategoryBadge,
  EmptyState,
  ErrorState,
  Field,
  PageHeader,
  Spinner,
  TableSkeleton,
} from "@/components/ui";
import {
  api,
  ApiError,
  CATEGORY_CODES,
  type CategoryCode,
  type Course,
  type ImportRowError,
  type Student,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useAsync, useDebounced } from "@/lib/hooks";

const PAGE_SIZE = 20;

/* ------------------------------------------------------------------ */
/* Create / edit form                                                  */
/* ------------------------------------------------------------------ */
function StudentForm({
  student,
  courses,
  onClose,
  onSaved,
}: {
  student: Student | null;
  courses: Course[];
  onClose: () => void;
  onSaved: (s: Student) => void;
}) {
  const sortedPrefs = [...(student?.preferences ?? [])].sort((a, b) => a.priority - b.priority);
  const [rollNo, setRollNo] = useState(student?.roll_no ?? "");
  const [name, setName] = useState(student?.name ?? "");
  const [marks, setMarks] = useState(student ? String(student.marks) : "");
  const [category, setCategory] = useState<CategoryCode>(student?.category.code ?? "General");
  const [appDate, setAppDate] = useState(student?.application_date ?? "");
  const [prefs, setPrefs] = useState<string[]>(
    [0, 1, 2].map((i) => (sortedPrefs[i] ? String(sortedPrefs[i].course_id) : "")),
  );
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    const preferences = prefs
      .filter((p) => p !== "")
      .map((p, i) => ({ course_id: Number(p), priority: i + 1 }));
    const body = {
      name,
      marks: Number(marks),
      category_code: category,
      application_date: appDate || null,
      preferences,
    };
    try {
      const saved = student
        ? await api.updateStudent(student.id, body)
        : await api.createStudent({ ...body, roll_no: rollNo });
      onSaved(saved);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Roll number" htmlFor="roll_no" hint={student ? "Roll numbers can't change." : undefined}>
          <input
            id="roll_no"
            className="input"
            required
            maxLength={30}
            value={rollNo}
            disabled={!!student}
            onChange={(e) => setRollNo(e.target.value)}
            placeholder="e.g. 20260123"
          />
        </Field>
        <Field label="Full name" htmlFor="name">
          <input
            id="name"
            className="input"
            required
            maxLength={120}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </Field>
        <Field label="Entrance marks" htmlFor="marks" hint="0 – 100">
          <input
            id="marks"
            className="input"
            type="number"
            required
            min={0}
            max={100}
            step={0.1}
            value={marks}
            onChange={(e) => setMarks(e.target.value)}
          />
        </Field>
        <Field label="Category" htmlFor="category">
          <select
            id="category"
            className="input"
            value={category}
            onChange={(e) => setCategory(e.target.value as CategoryCode)}
          >
            {CATEGORY_CODES.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </Field>
        <Field label="Application date" htmlFor="app_date" hint="Breaks ties on equal marks. Defaults to today.">
          <input
            id="app_date"
            className="input"
            type="date"
            value={appDate}
            onChange={(e) => setAppDate(e.target.value)}
          />
        </Field>
      </div>

      <fieldset>
        <legend className="label">Course preferences (in order)</legend>
        <div className="grid gap-3 sm:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <select
              key={i}
              aria-label={`Preference ${i + 1}`}
              className="input"
              value={prefs[i]}
              onChange={(e) => {
                const next = [...prefs];
                next[i] = e.target.value;
                setPrefs(next);
              }}
            >
              <option value="">{i + 1}. — none —</option>
              {courses
                .filter((c) => !prefs.some((p, j) => j !== i && p === String(c.id)))
                .map((c) => (
                  <option key={c.id} value={c.id}>
                    {i + 1}. {c.name}
                  </option>
                ))}
            </select>
          ))}
        </div>
        <p className="hint">Empty slots are skipped; the order of the filled ones is kept.</p>
      </fieldset>

      {error && (
        <p role="alert" className="alert-error">
          {error}
        </p>
      )}

      <div className="flex justify-end gap-2 border-t border-slate-100 pt-4 dark:border-slate-800">
        <button type="button" className="btn-secondary" onClick={onClose} disabled={busy}>
          Cancel
        </button>
        <button type="submit" className="btn-primary" disabled={busy}>
          {busy && <Spinner />} {student ? "Save changes" : "Register student"}
        </button>
      </div>
    </form>
  );
}

/* ------------------------------------------------------------------ */
/* CSV import                                                          */
/* ------------------------------------------------------------------ */
function ImportForm({ onClose, onImported }: { onClose: () => void; onImported: (n: number) => void }) {
  const toast = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rowErrors, setRowErrors] = useState<ImportRowError[]>([]);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    setRowErrors([]);
    try {
      const res = await api.importStudents(await file.text());
      onImported(res.created);
    } catch (err) {
      if (err instanceof ApiError && err.detail && typeof err.detail === "object" && "errors" in err.detail) {
        setRowErrors((err.detail as { errors: ImportRowError[] }).errors);
      }
      setError(err instanceof Error ? err.message : "Import failed");
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-4">
      <p className="text-sm text-slate-600 dark:text-slate-300">
        Columns: <code className="font-mono text-xs">roll_no, name, marks, category</code>, and
        optionally <code className="font-mono text-xs">application_date, preference_1…3</code>{" "}
        (course names). The import is all-or-nothing: if any row is invalid, nothing is saved.
      </p>
      <button
        type="button"
        className="btn-secondary btn-sm"
        onClick={() => api.downloadImportTemplate().catch((err) => toast.error(err.message))}
      >
        <Download className="h-3.5 w-3.5" /> Download template
      </button>
      <label
        htmlFor="csv"
        className="flex cursor-pointer flex-col items-center gap-2 rounded-lg border-2 border-dashed border-slate-300 px-6 py-8 text-center transition hover:border-brand-400 dark:border-slate-700 dark:hover:border-brand-600"
      >
        <FileUp className="h-6 w-6 text-slate-400" />
        <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
          {file ? file.name : "Choose a CSV file"}
        </span>
        <span className="text-xs text-slate-500">UTF-8, up to 1 MB / 5,000 rows</span>
        <input
          id="csv"
          type="file"
          accept=".csv,text/csv"
          className="sr-only"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
      </label>

      {error && (
        <div role="alert" className="alert-error flex-col gap-2">
          <p className="font-medium">{error}</p>
          {rowErrors.length > 0 && (
            <ul className="max-h-40 w-full space-y-1 overflow-y-auto text-xs">
              {rowErrors.map((r) => (
                <li key={r.row}>
                  <span className="font-mono font-semibold">Line {r.row}:</span> {r.message}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="flex justify-end gap-2 border-t border-slate-100 pt-4 dark:border-slate-800">
        <button type="button" className="btn-secondary" onClick={onClose} disabled={busy}>
          Cancel
        </button>
        <button type="submit" className="btn-primary" disabled={!file || busy}>
          {busy && <Spinner />} Import students
        </button>
      </div>
    </form>
  );
}

/* ------------------------------------------------------------------ */
/* Page                                                                */
/* ------------------------------------------------------------------ */
export default function StudentsPage() {
  const { isAdmin } = useAuth();
  const toast = useToast();
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<CategoryCode | "">("");
  const [page, setPage] = useState(0);
  const q = useDebounced(search.trim(), 300);

  const courses = useAsync(api.listCourses);
  const students = useAsync(
    () => api.listStudents({ q, category, limit: PAGE_SIZE, offset: page * PAGE_SIZE }),
    `${q}|${category}|${page}`,
  );

  const [editing, setEditing] = useState<Student | "new" | null>(null);
  const [importing, setImporting] = useState(false);
  const [deleting, setDeleting] = useState<Student | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  const courseName = (id: number) => courses.data?.find((c) => c.id === id)?.name ?? `#${id}`;
  const total = students.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const confirmDelete = async () => {
    if (!deleting) return;
    setDeleteBusy(true);
    try {
      await api.deleteStudent(deleting.id);
      toast.success(`Removed ${deleting.name}.`);
      setDeleting(null);
      students.reload();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setDeleteBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Students"
        subtitle="Applicants, their marks, category and ranked course preferences."
        actions={
          isAdmin && (
            <>
              <button type="button" className="btn-secondary" onClick={() => setImporting(true)}>
                <FileUp className="h-4 w-4" /> Import CSV
              </button>
              <button type="button" className="btn-primary" onClick={() => setEditing("new")}>
                <Plus className="h-4 w-4" /> Add student
              </button>
            </>
          )
        }
      />

      <div className="card">
        <div className="card-header">
          <div className="flex w-full flex-col gap-3 sm:flex-row sm:items-center">
            <div className="relative flex-1 sm:max-w-xs">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <input
                type="search"
                className="input pl-9"
                placeholder="Search name or roll no…"
                aria-label="Search students"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setPage(0);
                }}
              />
            </div>
            <select
              className="input sm:w-44"
              aria-label="Filter by category"
              value={category}
              onChange={(e) => {
                setCategory(e.target.value as CategoryCode | "");
                setPage(0);
              }}
            >
              <option value="">All categories</option>
              {CATEGORY_CODES.map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
            <p className="text-sm text-slate-500 dark:text-slate-400 sm:ml-auto">
              {students.data ? `${total} student${total === 1 ? "" : "s"}` : " "}
            </p>
          </div>
        </div>

        {students.error && (
          <div className="p-5">
            <ErrorState message={students.error} onRetry={students.reload} />
          </div>
        )}
        {!students.data && students.loading && <TableSkeleton cols={6} />}
        {students.data && students.data.items.length === 0 && (
          <EmptyState
            icon={Users}
            title={q || category ? "No matching students" : "No students yet"}
            description={
              q || category
                ? "Try a different search or category."
                : isAdmin
                  ? "Register students one by one or import a CSV."
                  : "Students will appear here once an admin registers them."
            }
          />
        )}
        {students.data && students.data.items.length > 0 && (
          <div className={students.loading ? "relative overflow-x-auto opacity-60" : "relative overflow-x-auto"}>
            <table className="table">
              <thead>
                <tr>
                  <th className="w-12 text-right">#</th>
                  <th>Student</th>
                  <th className="text-right">Marks</th>
                  <th>Category</th>
                  <th>Applied</th>
                  <th>Preferences</th>
                  {isAdmin && <th className="w-24"><span className="sr-only">Actions</span></th>}
                </tr>
              </thead>
              <tbody>
                {students.data.items.map((s, i) => (
                  <tr key={s.id}>
                    <td className="text-right text-xs tabular-nums text-slate-400">
                      {page * PAGE_SIZE + i + 1}
                    </td>
                    <td>
                      <div className="font-medium text-slate-900 dark:text-slate-100">{s.name}</div>
                      <div className="font-mono text-xs text-slate-500">{s.roll_no}</div>
                    </td>
                    <td className="text-right font-medium tabular-nums">{s.marks.toFixed(1)}</td>
                    <td>
                      <CategoryBadge code={s.category.code} />
                    </td>
                    <td className="whitespace-nowrap text-xs text-slate-500">{s.application_date}</td>
                    <td>
                      <ol className="flex flex-wrap gap-1">
                        {[...s.preferences]
                          .sort((a, b) => a.priority - b.priority)
                          .map((p) => (
                            <li key={p.course_id} className="badge-gray">
                              <span className="text-slate-400">{p.priority}.</span>
                              {courseName(p.course_id)}
                            </li>
                          ))}
                        {s.preferences.length === 0 && <li className="text-xs text-slate-400">—</li>}
                      </ol>
                    </td>
                    {isAdmin && (
                      <td>
                        <div className="flex justify-end gap-1">
                          <button
                            type="button"
                            className="btn-icon"
                            onClick={() => setEditing(s)}
                            aria-label={`Edit ${s.name}`}
                          >
                            <Pencil className="h-4 w-4" />
                          </button>
                          <button
                            type="button"
                            className="btn-icon hover:!text-red-600"
                            onClick={() => setDeleting(s)}
                            aria-label={`Delete ${s.name}`}
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
        )}

        {students.data && total > PAGE_SIZE && (
          <div className="flex items-center justify-between border-t border-slate-100 px-5 py-3 text-sm dark:border-slate-800">
            <p className="text-slate-500 dark:text-slate-400">
              Page {page + 1} of {pages}
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                className="btn-secondary btn-sm"
                disabled={page === 0}
                onClick={() => setPage((p) => p - 1)}
              >
                <ChevronLeft className="h-4 w-4" /> Previous
              </button>
              <button
                type="button"
                className="btn-secondary btn-sm"
                disabled={page + 1 >= pages}
                onClick={() => setPage((p) => p + 1)}
              >
                Next <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        )}
      </div>

      <Modal
        open={editing !== null}
        onClose={() => setEditing(null)}
        title={editing === "new" ? "Register student" : "Edit student"}
        description="Re-run the allocation afterwards to apply changes."
        size="lg"
      >
        {editing !== null && (
          <StudentForm
            key={editing === "new" ? "new" : editing.id}
            student={editing === "new" ? null : editing}
            courses={courses.data ?? []}
            onClose={() => setEditing(null)}
            onSaved={(s) => {
              toast.success(editing === "new" ? `Registered ${s.name}.` : `Saved ${s.name}.`);
              setEditing(null);
              students.reload();
            }}
          />
        )}
      </Modal>

      <Modal open={importing} onClose={() => setImporting(false)} title="Import students from CSV">
        {importing && (
          <ImportForm
            onClose={() => setImporting(false)}
            onImported={(n) => {
              toast.success(`Imported ${n} student${n === 1 ? "" : "s"}.`);
              setImporting(false);
              students.reload();
            }}
          />
        )}
      </Modal>

      <ConfirmDialog
        open={deleting !== null}
        title="Delete student?"
        message={
          deleting && (
            <>
              <strong>{deleting.name}</strong> ({deleting.roll_no}) and their preferences and
              allocation will be removed. This can&apos;t be undone.
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
