"""Pydantic request/response models."""
from datetime import date

from pydantic import BaseModel, ConfigDict, Field


# ---------- Categories ----------
class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str


# ---------- Students ----------
class PreferenceIn(BaseModel):
    course_id: int
    priority: int = Field(ge=1, le=3)


class StudentCreate(BaseModel):
    roll_no: str
    name: str
    marks: float = Field(ge=0, le=100)
    category_code: str  # General/OBC/SC/ST
    application_date: date | None = None
    preferences: list[PreferenceIn] = Field(default_factory=list, max_length=3)


class PreferenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    course_id: int
    priority: int


class StudentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    roll_no: str
    name: str
    marks: float
    category: CategoryOut
    application_date: date
    preferences: list[PreferenceOut]


# ---------- Courses ----------
class QuotaIn(BaseModel):
    category_code: str
    reserved_seats: int = Field(ge=0)


class CourseCreate(BaseModel):
    name: str
    total_seats: int = Field(ge=0)
    quotas: list[QuotaIn] = Field(default_factory=list)


class CourseUpdate(BaseModel):
    name: str | None = None
    total_seats: int | None = Field(default=None, ge=0)
    quotas: list[QuotaIn] | None = None


class QuotaOut(BaseModel):
    category_code: str
    reserved_seats: int


class CourseOut(BaseModel):
    id: int
    name: str
    total_seats: int
    open_seats: int
    quotas: list[QuotaOut]


# ---------- Allocations ----------
class AllocationOut(BaseModel):
    student_id: int
    roll_no: str
    student_name: str
    marks: float
    category_code: str
    course_id: int
    course_name: str
    seat_type: str
    preference_rank: int


class AllocationRunResult(BaseModel):
    total_students: int
    allocated: int
    unallocated: int
    allocations: list[AllocationOut]


# ---------- Dashboard ----------
class CourseStat(BaseModel):
    course_id: int
    course_name: str
    total_seats: int
    allocated: int
    available_seats: int
    applicants: int
    rejection_rate: float  # fraction 0..1


class CategoryStat(BaseModel):
    category_code: str
    allocated: int


class DashboardStats(BaseModel):
    total_students: int
    total_allocated: int
    total_unallocated: int
    course_stats: list[CourseStat]
    category_stats: list[CategoryStat]
    highest_rejection_course: str | None


# ---------- AI Assistant ----------
class AssistantQuery(BaseModel):
    question: str


class AssistantResponse(BaseModel):
    question: str
    sql: str | None
    rows: list[dict]
    answer: str
    source: str  # 'llm' | 'fallback'
