// Typed client for the FastAPI backend.
//
// Auth: the JWT from POST /auth/login is attached as a Bearer header. The token
// is held by AuthProvider (lib/auth.tsx), which registers it here via
// setAuthToken(). A 401 on any authenticated call fires `cas:unauthorized` so
// the provider can sign the user out.

export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(
  /\/+$/,
  "",
);

let authToken: string | null = null;

export function setAuthToken(token: string | null) {
  authToken = token;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public detail: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function describe(detail: unknown, status: number): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    // FastAPI/Pydantic validation errors
    return detail
      .map((d: { loc?: (string | number)[]; msg?: string }) => {
        const field = (d.loc ?? []).filter((p) => p !== "body").join(".");
        return field ? `${field}: ${d.msg}` : String(d.msg);
      })
      .join("; ");
  }
  if (detail && typeof detail === "object" && "message" in detail) {
    return String((detail as { message: unknown }).message);
  }
  if (status === 0) return "Cannot reach the server. Check your connection and try again.";
  return `Request failed (${status})`;
}

async function send(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  if (init.body && typeof init.body === "string" && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (authToken) headers.set("Authorization", `Bearer ${authToken}`);

  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...init, headers, cache: "no-store" });
  } catch {
    throw new ApiError(describe(undefined, 0), 0, undefined);
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    if (res.status === 401 && authToken && typeof window !== "undefined") {
      window.dispatchEvent(new Event("cas:unauthorized"));
    }
    throw new ApiError(describe(body.detail, res.status), res.status, body.detail);
  }
  return res;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await send(path, init);
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

async function download(path: string, fallbackName: string): Promise<void> {
  const res = await send(path);
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const name = /filename="?([^"]+)"?/.exec(disposition)?.[1] ?? fallbackName;
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// ------------------------------------------------------------------ types --
export type Role = "admin" | "viewer";
export type CategoryCode = "General" | "OBC" | "SC" | "ST";
export const CATEGORY_CODES: CategoryCode[] = ["General", "OBC", "SC", "ST"];
export const RESERVED_CATEGORIES = ["OBC", "SC", "ST"] as const;

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: Role;
}
export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  user: User;
}
export interface Meta {
  version: string;
  environment: string;
  demo_mode: boolean;
  llm_provider: "gemini" | "ollama" | "none" | string;
  llm_model: string | null;
  demo_accounts: { email: string; password: string; role: Role }[];
}
export interface Category {
  id: number;
  code: CategoryCode;
  name: string;
}
export interface Quota {
  category_code: string;
  reserved_seats: number;
}
export interface Course {
  id: number;
  name: string;
  total_seats: number;
  open_seats: number;
  applicants: number;
  quotas: Quota[];
}
export interface Preference {
  course_id: number;
  priority: number;
}
export interface Student {
  id: number;
  roll_no: string;
  name: string;
  marks: number;
  category: Category;
  application_date: string;
  preferences: Preference[];
}
export interface StudentInput {
  roll_no?: string;
  name: string;
  marks: number;
  category_code: CategoryCode;
  application_date?: string | null;
  preferences: Preference[];
}
export interface CourseInput {
  name: string;
  total_seats: number;
  quotas: Quota[];
}
export interface Allocation {
  student_id: number;
  roll_no: string;
  student_name: string;
  marks: number;
  category_code: CategoryCode;
  course_id: number;
  course_name: string;
  seat_type: "open" | "reserved";
  preference_rank: number;
}
export interface UnallocatedStudent {
  student_id: number;
  roll_no: string;
  student_name: string;
  marks: number;
  category_code: CategoryCode;
  preferences: string[];
}
export interface AllocationRun {
  id: number;
  run_at: string;
  total_students: number;
  allocated: number;
  triggered_by: string | null;
}
export interface AllocationRunResult {
  total_students: number;
  allocated: number;
  unallocated: number;
  run: AllocationRun;
  allocations: Allocation[];
}
export interface CourseStat {
  course_id: number;
  course_name: string;
  total_seats: number;
  allocated: number;
  available_seats: number;
  applicants: number;
  rejection_rate: number;
}
export interface DashboardStats {
  total_students: number;
  total_courses: number;
  total_seats: number;
  total_allocated: number;
  total_unallocated: number;
  allocation_rate: number;
  seat_fill_rate: number;
  course_stats: CourseStat[];
  category_stats: { category_code: CategoryCode; students: number; allocated: number }[];
  preference_stats: { preference_rank: number; allocated: number }[];
  seat_type_stats: { seat_type: "open" | "reserved"; allocated: number }[];
  highest_rejection_course: string | null;
  last_run: AllocationRun | null;
}
export interface AssistantResponse {
  question: string;
  sql: string | null;
  columns: string[];
  rows: Record<string, unknown>[];
  truncated: boolean;
  answer: string;
  source: "llm" | "fallback" | "none";
}
export interface ImportRowError {
  row: number;
  message: string;
}
export interface StudentQuery {
  q?: string;
  category?: CategoryCode | "";
  limit?: number;
  offset?: number;
}

// -------------------------------------------------------------- endpoints --
function qs(params: Record<string, string | number | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") search.set(k, String(v));
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

const json = (body: unknown) => JSON.stringify(body);

export const api = {
  meta: () => request<Meta>("/meta"),
  login: (email: string, password: string) =>
    request<TokenResponse>("/auth/login", { method: "POST", body: json({ email, password }) }),
  me: () => request<User>("/auth/me"),

  listStudents: async (query: StudentQuery = {}) => {
    const res = await send(`/students${qs({ ...query })}`);
    const items = (await res.json()) as Student[];
    return { items, total: Number(res.headers.get("X-Total-Count") ?? items.length) };
  },
  createStudent: (body: StudentInput) =>
    request<Student>("/students", { method: "POST", body: json(body) }),
  updateStudent: (id: number, body: Partial<StudentInput>) =>
    request<Student>(`/students/${id}`, { method: "PUT", body: json(body) }),
  deleteStudent: (id: number) => request<void>(`/students/${id}`, { method: "DELETE" }),
  importStudents: (csv: string) =>
    request<{ created: number }>("/students/import", {
      method: "POST",
      body: csv,
      headers: { "Content-Type": "text/csv" },
    }),
  downloadImportTemplate: () => download("/students/import/template", "students_template.csv"),

  listCourses: () => request<Course[]>("/courses"),
  createCourse: (body: CourseInput) =>
    request<Course>("/courses", { method: "POST", body: json(body) }),
  updateCourse: (id: number, body: Partial<CourseInput>) =>
    request<Course>(`/courses/${id}`, { method: "PUT", body: json(body) }),
  deleteCourse: (id: number) => request<void>(`/courses/${id}`, { method: "DELETE" }),

  runAllocation: () => request<AllocationRunResult>("/allocation/run", { method: "POST" }),
  listAllocations: (courseId?: number) =>
    request<Allocation[]>(`/allocation${qs({ course_id: courseId })}`),
  listUnallocated: () => request<UnallocatedStudent[]>("/allocation/unallocated"),
  listRuns: (limit = 10) => request<AllocationRun[]>(`/allocation/runs${qs({ limit })}`),
  exportAllocations: () => download("/allocation/export.csv", "allocation_results.csv"),

  stats: () => request<DashboardStats>("/dashboard/stats"),
  ask: (question: string) =>
    request<AssistantResponse>("/assistant/query", { method: "POST", body: json({ question }) }),
  resetDemo: () => request<void>("/admin/reset-demo", { method: "POST" }),
};
