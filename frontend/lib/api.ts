// Thin typed API client for the FastAPI backend.
const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(API_KEY ? { "X-API-Key": API_KEY } : {}),
    },
    cache: "no-store",
    ...init,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || `Request failed: ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export interface Category { id: number; code: string; name: string }
export interface Quota { category_code: string; reserved_seats: number }
export interface Course {
  id: number; name: string; total_seats: number; open_seats: number; quotas: Quota[];
}
export interface Preference { course_id: number; priority: number }
export interface Student {
  id: number; roll_no: string; name: string; marks: number;
  category: Category; application_date: string; preferences: Preference[];
}
export interface Allocation {
  student_id: number; roll_no: string; student_name: string; marks: number;
  category_code: string; course_id: number; course_name: string;
  seat_type: string; preference_rank: number;
}
export interface AllocationRun {
  total_students: number; allocated: number; unallocated: number; allocations: Allocation[];
}
export interface CourseStat {
  course_id: number; course_name: string; total_seats: number; allocated: number;
  available_seats: number; applicants: number; rejection_rate: number;
}
export interface CategoryStat { category_code: string; allocated: number }
export interface DashboardStats {
  total_students: number; total_allocated: number; total_unallocated: number;
  course_stats: CourseStat[]; category_stats: CategoryStat[];
  highest_rejection_course: string | null;
}
export interface AssistantResponse {
  question: string; sql: string | null; rows: Record<string, unknown>[];
  answer: string; source: string;
}

export const api = {
  listCourses: () => request<Course[]>("/courses"),
  createCourse: (body: unknown) =>
    request<Course>("/courses", { method: "POST", body: JSON.stringify(body) }),
  listStudents: () => request<Student[]>("/students"),
  createStudent: (body: unknown) =>
    request<Student>("/students", { method: "POST", body: JSON.stringify(body) }),
  deleteStudent: (id: number) => request<void>(`/students/${id}`, { method: "DELETE" }),
  runAllocation: () => request<AllocationRun>("/allocation/run", { method: "POST" }),
  listAllocations: () => request<Allocation[]>("/allocation"),
  stats: () => request<DashboardStats>("/dashboard/stats"),
  ask: (question: string) =>
    request<AssistantResponse>("/assistant/query", {
      method: "POST",
      body: JSON.stringify({ question }),
    }),
};
